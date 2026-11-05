import array
import math
import random
import sys
import pygame

# Инициализация аудио и экрана
pygame.mixer.pre_init(22050, -16, 1, 512)
pygame.init()
WIDTH, HEIGHT = 1150, 740
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("PARKING ULTIMATE EDITION")
clock = pygame.time.Clock()


def get_font(size, bold=False):
    for name in ["Segoe UI", "Verdana", "Arial", "DejaVu Sans"]:
        f = pygame.font.SysFont(name, size, bold=bold)
        if f:
            return f
    return pygame.font.Font(None, size)


font_xs = get_font(13, False)
font_sm = get_font(16, True)
font_md = get_font(23, True)
font_lg = get_font(40, True)


# ==========================================
# 1. ПРОЦЕДУРНЫЙ СИНТЕЗАТОР ЗВУКА (БЕЗ MP3)
# ==========================================
class SoundEngine:

    def __init__(self):
        self.enabled = pygame.mixer.get_init() is not None
        if not self.enabled:
            return
        self.beep_hi = self._tone(1350, 0.055, 0.22, "sine")
        self.beep_mid = self._tone(980, 0.075, 0.18, "sine")
        self.rev_beep = self._tone(780, 0.14, 0.14, "square")
        self.crash = self._noise(0.32, 0.45, decay=True)
        self.tire = self._screech(0.12, 0.14)
        self.horn = self._chord([410, 515], 0.28, 0.25)
        self.win = self._arp([523, 659, 784, 1046], 0.11, 0.28)
        self.eng_idle = self._engine_loop(62, 0.14)
        self.eng_drive = self._engine_loop(105, 0.18)

        self.eng_channel = pygame.mixer.Channel(0)
        self.fx_channel = pygame.mixer.Channel(1)
        self.eng_mode = 0  # 0 stop, 1 idle, 2 drive

    def _tone(self, freq, dur, vol, kind="sine"):
        sr = 22050
        n = int(sr * dur)
        buf = array.array("h")
        for i in range(n):
            t = i / sr
            env = 1.0 - (i / n) * 0.6
            if kind == "sine":
                v = math.sin(2 * math.pi * freq * t)
            else:
                v = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
            buf.append(int(v * 32767 * vol * env))
        return pygame.mixer.Sound(buffer=buf)

    def _chord(self, freqs, dur, vol):
        sr = 22050
        n = int(sr * dur)
        buf = array.array("h")
        for i in range(n):
            t = i / sr
            s = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
            # легкий тембр автомобильного клаксона
            s = max(-1.0, min(1.0, s * 1.6))
            buf.append(int(s * 32767 * vol))
        return pygame.mixer.Sound(buffer=buf)

    def _arp(self, freqs, note_dur, vol):
        sr = 22050
        buf = array.array("h")
        for f in freqs:
            n = int(sr * note_dur)
            for i in range(n):
                t = i / sr
                env = 1.0 - (i / n) * 0.5
                v = math.sin(2 * math.pi * f * t)
                buf.append(int(v * 32767 * vol * env))
        return pygame.mixer.Sound(buffer=buf)

    def _noise(self, dur, vol, decay=True):
        sr = 22050
        n = int(sr * dur)
        buf = array.array("h")
        last = 0.0
        for i in range(n):
            env = (1.0 - i / n) ** 2 if decay else 1.0
            raw = random.uniform(-1, 1)
            last = last * 0.72 + raw * 0.28  # Низкочастотный удар металла
            buf.append(int(last * 32767 * vol * env))
        return pygame.mixer.Sound(buffer=buf)

    def _screech(self, dur, vol):
        sr = 22050
        n = int(sr * dur)
        buf = array.array("h")
        for i in range(n):
            t = i / sr
            mod = math.sin(2 * math.pi * 38 * t) * 140
            v = math.sin(2 * math.pi * (1650 + mod) * t) * 0.7 + random.uniform(
                -0.3, 0.3
            )
            buf.append(int(max(-1, min(1, v)) * 32767 * vol))
        return pygame.mixer.Sound(buffer=buf)

    def _engine_loop(self, base_freq, vol):
        sr = 22050
        n = int(sr / base_freq) * 16
        buf = array.array("h")
        for i in range(n):
            t = i / sr
            v = (
                math.sin(2 * math.pi * base_freq * t) * 0.6
                + math.sin(2 * math.pi * base_freq * 2 * t) * 0.25
                + math.sin(2 * math.pi * base_freq * 0.5 * t) * 0.15
            )
            buf.append(int(v * 32767 * vol))
        return pygame.mixer.Sound(buffer=buf)

    def set_engine(self, moving):
        if not self.enabled:
            return
        want = 2 if moving else 1
        if want != self.eng_mode:
            self.eng_mode = want
            snd = self.eng_drive if moving else self.eng_idle
            self.eng_channel.play(snd, loops=-1)

    def stop_engine(self):
        if self.enabled:
            self.eng_channel.stop()
            self.eng_mode = 0

    def play(self, snd):
        if self.enabled:
            snd.play()


sfx = SoundEngine()


# ==========================================
# 2. ГЕОМЕТРИЯ, COLLISIONS И ЧАСТИЦЫ
# ==========================================
def get_rotated_vertices(x, y, w, h, angle_deg):
    rad = math.radians(angle_deg)
    ca, sa = math.cos(rad), math.sin(rad)
    hw, hh = w / 2, h / 2
    return [
        (x + lx * ca - ly * sa, y + lx * sa + ly * ca)
        for lx, ly in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    ]


def check_sat_collision(poly1, poly2):
    for poly in (poly1, poly2):
        for i in range(len(poly)):
            p1, p2 = poly[i], poly[(i + 1) % len(poly)]
            nx, ny = p2[1] - p1[1], p1[0] - p2[0]
            proj1 = [p[0] * nx + p[1] * ny for p in poly1]
            proj2 = [p[0] * nx + p[1] * ny for p in poly2]
            if max(proj1) < min(proj2) or max(proj2) < min(proj1):
                return False
    return True


def point_to_poly_dist(px, py, poly):
    best = 9999.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        t = (
            0
            if l2 == 0
            else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
        )
        cx, cy = x1 + t * dx, y1 + t * dy
        best = min(best, math.hypot(px - cx, py - cy))
    return best


class Particle:

    def __init__(self, x, y, vx, vy, color, size, life, grow=0.14):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.color = color
        self.size = size
        self.life = self.max_life = life
        self.grow = grow

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.94
        self.vy *= 0.94
        self.size += self.grow
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0 or self.size <= 0.5:
            return
        r = int(self.size)
        alpha = max(0, min(255, int(235 * (self.life / self.max_life))))
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (r, r), r)
        surf.blit(s, (int(self.x - r), int(self.y - r)))


# ==========================================
# 3. АВТОПАРК И ГЕНЕРАЦИЯ КУЗОВОВ
# ==========================================
CAR_SPECS = [
    {
        "id": "smart",
        "name": "СМАРТ СИТИ",
        "desc": "Компактный и юркий. Идеален для узких щелей.",
        "unlock_stars": 0,
        "w": 48,
        "h": 28,
        "color": (50, 175, 235),
        "stripes": False,
        "accel": 0.16,
        "max_spd": 4.2,
        "steer": 37.0,
        "drift": 0.0,
    },
    {
        "id": "sport",
        "name": "СПОРТКАР GT",
        "desc": "Идеальный баланс скорости, габаритов и рулежки.",
        "unlock_stars": 0,
        "w": 64,
        "h": 32,
        "color": (215, 35, 45),
        "stripes": True,
        "accel": 0.15,
        "max_spd": 4.8,
        "steer": 32.0,
        "drift": 0.12,
    },
    {
        "id": "muscle",
        "name": "МАСЛКАР V8",
        "desc": "Дикий крутящий момент! Уходит в занос на газу.",
        "unlock_stars": 4,
        "w": 68,
        "h": 33,
        "color": (240, 155, 25),
        "stripes": True,
        "accel": 0.19,
        "max_spd": 5.3,
        "steer": 34.0,
        "drift": 0.86,
    },
    {
        "id": "limo",
        "name": "ЛИМУЗИН VIP",
        "desc": "Огромная база. Требует широкого захода в поворот.",
        "unlock_stars": 9,
        "w": 96,
        "h": 32,
        "color": (235, 235, 242),
        "stripes": False,
        "accel": 0.11,
        "max_spd": 3.9,
        "steer": 26.0,
        "drift": 0.05,
    },
]


def create_car_body_surface(w, h, color, stripes=False):
    surf = pygame.Surface((w + 16, h + 16), pygame.SRCALPHA)
    ox, oy = 8, 8
    dark = tuple(max(0, c - 45) for c in color)
    light = tuple(min(255, c + 35) for c in color)

    # Зеркала
    pygame.draw.polygon(
        surf,
        color,
        [(ox + w * 0.65, oy), (ox + w * 0.72, oy - 5), (ox + w * 0.76, oy)],
    )
    pygame.draw.polygon(
        surf,
        color,
        [
            (ox + w * 0.65, oy + h),
            (ox + w * 0.72, oy + h + 5),
            (ox + w * 0.76, oy + h),
        ],
    )

    pygame.draw.rect(surf, dark, (ox, oy, w, h), border_radius=8)
    pygame.draw.rect(
        surf, color, (ox + 2, oy + 2, w - 4, h - 4), border_radius=7
    )

    if stripes:
        sc = (30, 30, 35) if sum(color) > 450 else (240, 240, 245)
        pygame.draw.rect(surf, sc, (ox + 3, oy + h // 2 - 4, w - 6, 3))
        pygame.draw.rect(surf, sc, (ox + 3, oy + h // 2 + 1, w - 6, 3))

    pygame.draw.line(
        surf, light, (ox + w * 0.72, oy + 6), (ox + w - 5, oy + 8), 2
    )
    pygame.draw.line(
        surf, light, (ox + w * 0.72, oy + h - 6), (ox + w - 5, oy + h - 8), 2
    )

    # Салон и стекла
    pygame.draw.rect(
        surf,
        (20, 24, 32),
        (ox + w * 0.15, oy + 4, w * 0.58, h - 8),
        border_radius=5,
    )
    glass = (52, 78, 102)
    pygame.draw.polygon(
        surf,
        glass,
        [
            (ox + w * 0.56, oy + 6),
            (ox + w * 0.72, oy + 5),
            (ox + w * 0.72, oy + h - 5),
            (ox + w * 0.56, oy + h - 6),
        ],
    )
    pygame.draw.polygon(
        surf,
        glass,
        [
            (ox + w * 0.17, oy + 6),
            (ox + w * 0.27, oy + 7),
            (ox + w * 0.27, oy + h - 7),
            (ox + w * 0.17, oy + h - 6),
        ],
    )
    pygame.draw.rect(
        surf, color, (ox + w * 0.26, oy + 6, w * 0.31, h - 12), border_radius=4
    )

    # Оптика
    pygame.draw.rect(
        surf, (255, 250, 210), (ox + w - 4, oy + 3, 4, 7), border_radius=2
    )
    pygame.draw.rect(
        surf, (255, 250, 210), (ox + w - 4, oy + h - 10, 4, 7), border_radius=2
    )
    pygame.draw.rect(
        surf, (135, 18, 22), (ox, oy + 3, 4, 7), border_radius=2
    )
    pygame.draw.rect(
        surf, (135, 18, 22), (ox, oy + h - 10, 4, 7), border_radius=2
    )
    return surf


def create_trailer_surface(w, h):
    surf = pygame.Surface((w + 16, h + 16), pygame.SRCALPHA)
    ox, oy = 8, 8
    pygame.draw.rect(surf, (65, 70, 80), (ox, oy, w, h), border_radius=5)
    pygame.draw.rect(
        surf, (185, 192, 205), (ox + 3, oy + 3, w - 6, h - 6), border_radius=4
    )
    # Ребра жесткости тента
    for rx in range(12, w - 8, 12):
        pygame.draw.line(
            surf, (145, 152, 165), (ox + rx, oy + 4), (ox + rx, oy + h - 4), 2
        )
    # Габаритные огни прицепа
    pygame.draw.rect(surf, (210, 40, 40), (ox, oy + 3, 3, 6))
    pygame.draw.rect(surf, (210, 40, 40), (ox, oy + h - 9, 3, 6))
    return surf


# ==========================================
# 4. ПРИЦЕП И МАШИНА ИГРОКА (С ДРИФТОМ, ДВОРНИКАМИ И ПАРКТРОНИКОМ)
# ==========================================
class Trailer:

    def __init__(self, hitch_x, hitch_y, angle):
        self.w, self.h = 54, 30
        self.link_dist = 34  # Расстояние от фаркопа до оси прицепа
        self.angle = angle
        rad = math.radians(angle)
        self.x = hitch_x - math.cos(rad) * self.link_dist
        self.y = hitch_y - math.sin(rad) * self.link_dist
        self.surf = create_trailer_surface(self.w, self.h)

    def update(self, hitch_x, hitch_y):
        dx = hitch_x - self.x
        dy = hitch_y - self.y
        target_angle = math.degrees(math.atan2(dy, dx))
        self.angle = target_angle
        rad = math.radians(self.angle)
        self.x = hitch_x - math.cos(rad) * self.link_dist
        self.y = hitch_y - math.sin(rad) * self.link_dist

    def get_vertices(self):
        return get_rotated_vertices(
            self.x, self.y, self.w - 3, self.h - 3, self.angle
        )

    def draw(self, surf, hitch_x, hitch_y):
        # Дышло сцепки
        pygame.draw.line(
            surf,
            (40, 42, 48),
            (int(hitch_x), int(hitch_y)),
            (int(self.x), int(self.y)),
            5,
        )
        pygame.draw.circle(
            surf, (220, 180, 40), (int(hitch_x), int(hitch_y)), 4
        )

        # Тень и кузов прицепа
        sh = pygame.Surface((self.w + 16, self.h + 16), pygame.SRCALPHA)
        pygame.draw.rect(
            sh, (0, 0, 0, 95), (8, 8, self.w, self.h), border_radius=6
        )
        r_sh = pygame.transform.rotate(sh, -self.angle)
        surf.blit(r_sh, r_sh.get_rect(center=(self.x + 5, self.y + 6)).topleft)

        r_body = pygame.transform.rotate(self.surf, -self.angle)
        surf.blit(r_body, r_body.get_rect(center=(self.x, self.y)).topleft)


class PlayerCar:

    def __init__(self, spec):
        self.apply_spec(spec)
        self.reset(200, 200, 0, False)

    def apply_spec(self, spec):
        self.spec = spec
        self.w, self.h = spec["w"], spec["h"]
        self.accel = spec["accel"]
        self.max_speed = spec["max_spd"]
        self.max_rev = -2.5
        self.max_steer = spec["steer"]
        self.drift_factor = spec["drift"]
        self.body_surf = create_car_body_surface(
            self.w, self.h, spec["color"], spec["stripes"]
        )

    def reset(self, x, y, angle, with_trailer=False):
        self.x, self.y, self.angle = x, y, angle
        self.vx = self.vy = 0.0
        self.speed = 0.0
        self.steer_angle = 0.0
        self.braking = False
        self.reversing = False
        self.hp = 3
        self.invuln = 0
        self.scratches = []
        self.sensor_front = 999.0
        self.sensor_rear = 999.0
        self.trailer = None
        if with_trailer:
            hx, hy = self.get_hitch_pos()
            self.trailer = Trailer(hx, hy, angle)

    def get_hitch_pos(self):
        rad = math.radians(self.angle)
        return (
            self.x - math.cos(rad) * (self.w * 0.52),
            self.y - math.sin(rad) * (self.w * 0.52),
        )

    def update(self, weather, particles, skidmarks, ticks):
        if self.invuln > 0:
            self.invuln -= 1

        keys = pygame.key.get_pressed()
        self.braking = False
        self.reversing = False
        throttling = False

        # Погодные модификаторы сцепления
        grip = 0.24
        friction = 0.036
        brake_p = 0.25
        if weather == "rain":
            grip = 0.15
            friction = 0.025
            brake_p = 0.16
        elif weather == "ice":
            grip = 0.065
            friction = 0.012
            brake_p = 0.085

        if self.drift_factor > 0.5:
            grip *= 0.52  # Маслкар метет хвостом

        # Руль
        target_steer = 0.0
        if keys[pygame.K_a]:
            target_steer = -self.max_steer
        if keys[pygame.K_d]:
            target_steer = self.max_steer
        self.steer_angle += (target_steer - self.steer_angle) * 0.22

        # Педали
        if keys[pygame.K_SPACE]:
            self.braking = True
            if abs(self.speed) > 1.3:
                if ticks % 9 == 0:
                    sfx.play(sfx.tire)
                rad = math.radians(self.angle)
                ca, sa = math.cos(rad), math.sin(rad)
                for wy in (-self.h * 0.36, self.h * 0.36):
                    wx = self.x - self.w * 0.32 * ca - wy * sa
                    w_y = self.y - self.w * 0.32 * sa + wy * ca
                    col_skid = (
                        (180, 210, 235, 90)
                        if weather == "ice"
                        else (18, 18, 22, 145)
                    )
                    pygame.draw.circle(
                        skidmarks, col_skid, (int(wx), int(w_y)), 3
                    )
            if self.speed > 0:
                self.speed = max(0.0, self.speed - brake_p)
            elif self.speed < 0:
                self.speed = min(0.0, self.speed + brake_p)
        else:
            if keys[pygame.K_w]:
                self.speed += self.accel
                throttling = True
            elif keys[pygame.K_s]:
                self.speed -= self.accel
                self.reversing = True
            else:
                if self.speed > 0:
                    self.speed = max(0.0, self.speed - friction)
                elif self.speed < 0:
                    self.speed = min(0.0, self.speed + friction)

        self.speed = max(self.max_rev, min(self.max_speed, self.speed))
        sfx.set_engine(throttling or self.reversing or abs(self.speed) > 0.4)

        if self.reversing and ticks % 34 == 0:
            sfx.play(sfx.rev_beep)

        # Поворот кузова
        if abs(self.speed) > 0.04:
            turn_rate = (self.steer_angle / self.max_steer) * (175.0 / self.w)
            direction = 1 if self.speed > 0 else -1
            spd_f = min(abs(self.speed) / 1.3, 1.0)
            self.angle += turn_rate * direction * spd_f

        # Вектор скорости с инерцией и заносом (дрифтом)
        rad = math.radians(self.angle)
        want_vx = math.cos(rad) * self.speed
        want_vy = math.sin(rad) * self.speed
        self.vx += (want_vx - self.vx) * grip
        self.vy += (want_vy - self.vy) * grip

        # Следы при боковом заносе
        lateral_slip = math.hypot(self.vx - want_vx, self.vy - want_vy)
        if lateral_slip > 0.65 and abs(self.speed) > 1.5:
            ca, sa = math.cos(rad), math.sin(rad)
            for wy in (-self.h * 0.36, self.h * 0.36):
                wx = self.x - self.w * 0.32 * ca - wy * sa
                w_y = self.y - self.w * 0.32 * sa + wy * ca
                pygame.draw.circle(
                    skidmarks, (22, 22, 26, 110), (int(wx), int(w_y)), 3
                )
            if random.random() < 0.4:
                particles.append(
                    Particle(
                        wx, w_y, 0, 0, (200, 205, 215), 4, 18, 0.22
                    )
                )

        self.x += self.vx
        self.y += self.vy

        # Выхлоп
        if (throttling or self.reversing) and random.random() < 0.4:
            ex = self.x - math.cos(rad) * (self.w * 0.52) + math.sin(rad) * 8
            ey = self.y - math.sin(rad) * (self.w * 0.52) - math.cos(rad) * 8
            particles.append(
                Particle(
                    ex,
                    ey,
                    -math.cos(rad) * 0.6,
                    -math.sin(rad) * 0.6,
                    (155, 160, 170),
                    3,
                    20,
                    0.16,
                )
            )

        if self.trailer:
            hx, hy = self.get_hitch_pos()
            self.trailer.update(hx, hy)

    def bounce_damage(self, particles):
        if self.invuln > 0:
            return False
        sfx.play(sfx.crash)
        # Сильный удар на полном ходу снимает сразу 2 HP
        dmg = 2 if abs(self.speed) > 3.6 else 1
        self.hp -= dmg
        self.invuln = 42
        self.speed = -self.speed * 0.45
        self.vx = -self.vx * 0.55
        self.vy = -self.vy * 0.55
        # Добавляем визуальную вмятину/царапину на кузов
        self.scratches.append((
            random.uniform(-self.w * 0.35, self.w * 0.35),
            random.choice([-self.h * 0.38, self.h * 0.38]),
        ))
        for _ in range(26):
            a = random.uniform(0, math.pi * 2)
            s = random.uniform(1.5, 5.5)
            particles.append(
                Particle(
                    self.x,
                    self.y,
                    math.cos(a) * s,
                    math.sin(a) * s,
                    random.choice([(255, 200, 40), (255, 110, 20), (255, 255, 255)]),
                    4,
                    24,
                    -0.08,
                )
            )
        return self.hp <= 0

    def get_vertices(self):
        return get_rotated_vertices(
            self.x, self.y, self.w - 4, self.h - 4, self.angle
        )

    def update_sensors(self, obstacle_polys, sensors_on, ticks):
        if not sensors_on:
            self.sensor_front = self.sensor_rear = 999.0
            return
        rad = math.radians(self.angle)
        fx = self.x + math.cos(rad) * (self.w * 0.5)
        fy = self.y + math.sin(rad) * (self.w * 0.5)

        if self.trailer:
            trad = math.radians(self.trailer.angle)
            rx = self.trailer.x - math.cos(trad) * (self.trailer.w * 0.5)
            ry = self.trailer.y - math.sin(trad) * (self.trailer.w * 0.5)
        else:
            rx = self.x - math.cos(rad) * (self.w * 0.5)
            ry = self.y - math.sin(rad) * (self.w * 0.5)

        df = dr = 999.0
        for poly in obstacle_polys:
            df = min(df, point_to_poly_dist(fx, fy, poly))
            dr = min(dr, point_to_poly_dist(rx, ry, poly))
        self.sensor_front, self.sensor_rear = df, dr

        closest = min(df, dr)
        if closest < 58:
            interval = 8 if closest < 20 else (16 if closest < 36 else 28)
            if ticks % interval == 0:
                sfx.play(sfx.beep_hi if closest < 24 else sfx.beep_mid)

    def draw(self, surf, weather, sensors_on, ticks):
        if self.trailer:
            hx, hy = self.get_hitch_pos()
            self.trailer.draw(surf, hx, hy)

        # Мерцание после легкого удара
        if self.invuln > 0 and (self.invuln // 4) % 2 == 1:
            return

        rad = math.radians(self.angle)
        ca, sa = math.cos(rad), math.sin(rad)

        # Тень
        sh = pygame.Surface((self.w + 20, self.h + 20), pygame.SRCALPHA)
        pygame.draw.rect(
            sh, (0, 0, 0, 105), (10, 10, self.w, self.h), border_radius=10
        )
        r_sh = pygame.transform.rotate(sh, -self.angle)
        surf.blit(r_sh, r_sh.get_rect(center=(self.x + 5, self.y + 6)).topleft)

        # Колеса
        for lx, ly, wa in [
            (-self.w * 0.32, -self.h * 0.45, 0),
            (-self.w * 0.32, self.h * 0.45, 0),
            (self.w * 0.32, -self.h * 0.45, self.steer_angle),
            (self.w * 0.32, self.h * 0.45, self.steer_angle),
        ]:
            wx, wy = self.x + lx * ca - ly * sa, self.y + lx * sa + ly * ca
            ws = pygame.Surface((14, 7), pygame.SRCALPHA)
            pygame.draw.rect(ws, (15, 15, 18), (0, 0, 14, 7), border_radius=2)
            r_ws = pygame.transform.rotate(ws, -(self.angle + wa))
            surf.blit(r_ws, r_ws.get_rect(center=(wx, wy)).topleft)

        # Конусы фар
        beam = pygame.Surface((240, 140), pygame.SRCALPHA)
        pygame.draw.polygon(
            beam, (255, 250, 200, 30), [(0, 58), (225, 10), (225, 68)]
        )
        pygame.draw.polygon(
            beam, (255, 250, 200, 30), [(0, 82), (225, 72), (225, 130)]
        )
        fx, fy = self.x + ca * (self.w * 0.48), self.y + sa * (self.w * 0.48)
        r_bm = pygame.transform.rotate(beam, -self.angle)
        surf.blit(
            r_bm,
            (
                fx + ca * 115 - r_bm.get_width() / 2,
                fy + sa * 115 - r_bm.get_height() / 2,
            ),
        )

        # Кузов
        r_body = pygame.transform.rotate(self.body_surf, -self.angle)
        surf.blit(r_body, r_body.get_rect(center=(self.x, self.y)).topleft)

        # Царапины на кузове от столкновений
        for sx, sy in self.scratches:
            px, py = self.x + sx * ca - sy * sa, self.y + sx * sa + sy * ca
            pygame.draw.line(
                surf, (35, 35, 40), (px - 3, py - 3), (px + 3, py + 3), 2
            )

        # Работающие дворники на лобовом стекле во время дождя!
        if weather == "rain":
            sweep = math.sin(ticks * 0.014) * 0.55
            for wy_off in (-6, 5):
                bx = self.x + (self.w * 0.20) * ca - wy_off * sa
                by = self.y + (self.w * 0.20) * sa + wy_off * ca
                ang_w = rad + math.pi / 2 + sweep
                ex, ey = bx + math.cos(ang_w) * 8, by + math.sin(ang_w) * 8
                pygame.draw.line(surf, (25, 28, 32), (bx, by), (ex, ey), 2)

        # Стоп-сигналы и задний ход
        if self.braking or self.reversing:
            for ly in (-self.h * 0.34, self.h * 0.34):
                tx = self.x - (self.w * 0.48) * ca - ly * sa
                ty = self.y - (self.w * 0.48) * sa + ly * ca
                gs = pygame.Surface((28, 28), pygame.SRCALPHA)
                if self.braking:
                    pygame.draw.circle(gs, (255, 25, 25, 120), (14, 14), 13)
                    pygame.draw.circle(gs, (255, 200, 200, 240), (14, 14), 4)
                else:
                    pygame.draw.circle(gs, (255, 255, 255, 95), (14, 14), 10)
                    pygame.draw.circle(gs, (255, 255, 255, 240), (14, 14), 3)
                surf.blit(gs, (tx - 14, ty - 14))

        # Визуальные волны ПАРКТРОНИКА (спереди и сзади)
        if sensors_on:
            self._draw_radar_waves(
                surf, fx, fy, self.angle, self.sensor_front
            )
            if self.trailer:
                trad = math.radians(self.trailer.angle)
                rx = self.trailer.x - math.cos(trad) * (self.trailer.w * 0.5)
                ry = self.trailer.y - math.sin(trad) * (self.trailer.w * 0.5)
                self._draw_radar_waves(
                    surf, rx, ry, self.trailer.angle + 180, self.sensor_rear
                )
            else:
                rx = self.x - ca * (self.w * 0.5)
                ry = self.y - sa * (self.w * 0.5)
                self._draw_radar_waves(
                    surf, rx, ry, self.angle + 180, self.sensor_rear
                )

    def _draw_radar_waves(self, surf, bx, by, ang_deg, dist):
        if dist > 62:
            return
        col = (
            (255, 45, 45)
            if dist < 22
            else ((255, 195, 35) if dist < 40 else (50, 235, 100))
        )
        base_rad = math.radians(ang_deg)
        arcs = 1 if dist < 22 else (2 if dist < 40 else 3)
        for i in range(1, arcs + 1):
            r = 10 + i * 9
            pts = []
            for a in range(-36, 37, 12):
                ar = base_rad + math.radians(a)
                pts.append((bx + math.cos(ar) * r, by + math.sin(ar) * r))
            if len(pts) > 1:
                pygame.draw.lines(surf, col, False, pts, 2)


# ==========================================
# 5. ЖИВОЙ МИР: ТРАФИК, ПЕШЕХОДЫ, ШЛАГБАУМЫ И «ИЗЮМИНКА»
# ==========================================
class ParkedCar:

    def __init__(self, x, y, angle, color):
        self.x, self.y, self.angle = x, y, angle
        self.w, self.h = 62, 31
        base = create_car_body_surface(self.w, self.h, color)
        sh = pygame.Surface((self.w + 18, self.h + 18), pygame.SRCALPHA)
        pygame.draw.rect(
            sh, (0, 0, 0, 95), (9, 9, self.w, self.h), border_radius=9
        )
        self.r_sh = pygame.transform.rotate(sh, -angle)
        self.r_bd = pygame.transform.rotate(base, -angle)
        self.verts = get_rotated_vertices(x, y, self.w - 4, self.h - 4, angle)

    def draw(self, surf):
        surf.blit(
            self.r_sh, self.r_sh.get_rect(center=(self.x + 5, self.y + 6)).topleft
        )
        surf.blit(
            self.r_bd, self.r_bd.get_rect(center=(self.x, self.y)).topleft
        )


class TrafficCar:

    def __init__(self, x1, y1, x2, y2, speed, color):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.x, self.y = x1, y1
        self.base_speed = speed
        self.w, self.h = 62, 31
        self.angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        base = create_car_body_surface(self.w, self.h, color)
        self.r_bd = pygame.transform.rotate(base, -self.angle)
        self.horn_cd = 0

    def update(self, player):
        if self.horn_cd > 0:
            self.horn_cd -= 1
        rad = math.radians(self.angle)
        fx = self.x + math.cos(rad) * 68
        fy = self.y + math.sin(rad) * 68

        # Проверяем, не перегородил ли игрок дорогу трафику
        dist_player = math.hypot(player.x - fx, player.y - fy)
        if player.trailer:
            dist_player = min(
                dist_player,
                math.hypot(player.trailer.x - fx, player.trailer.y - fy),
            )

        if dist_player < 62:
            if self.horn_cd == 0:
                sfx.play(sfx.horn)
                self.horn_cd = 95
            return  # Экстренно ждёт, пока игрок проедет

        self.x += math.cos(rad) * self.base_speed
        self.y += math.sin(rad) * self.base_speed
        if math.hypot(self.x - self.x1, self.y - self.y1) > math.hypot(
            self.x2 - self.x1, self.y2 - self.y1
        ):
            self.x, self.y = self.x1, self.y1

    def get_vertices(self):
        return get_rotated_vertices(
            self.x, self.y, self.w - 4, self.h - 4, self.angle
        )

    def draw(self, surf):
        surf.blit(
            self.r_bd, self.r_bd.get_rect(center=(self.x, self.y)).topleft
        )
        if self.horn_cd > 65:
            txt = font_xs.render("БИ-БИП!", True, (255, 230, 50))
            surf.blit(txt, (self.x - 22, self.y - 34))


class Pedestrian:

    def __init__(self, x1, y1, x2, y2, speed=1.1):
        self.p1, self.p2 = (x1, y1), (x2, y2)
        self.x, self.y = float(x1), float(y1)
        self.target = self.p2
        self.speed = speed
        self.shirt = random.choice(
            [(235, 95, 95), (85, 175, 245), (95, 215, 130), (240, 195, 70)]
        )
        self.step = 0.0

    def update(self, player):
        if math.hypot(player.x - self.x, player.y - self.y) < 48:
            return  # Пугается и останавливается перед бампером
        tx, ty = self.target
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d < 4:
            self.target = self.p1 if self.target == self.p2 else self.p2
        else:
            self.x += (dx / d) * self.speed
            self.y += (dy / d) * self.speed
            self.step += 0.22

    def get_vertices(self):
        return get_rotated_vertices(self.x, self.y, 14, 14, 0)

    def draw(self, surf):
        # Зебра под маршрутом пешехода
        x1, y1 = self.p1
        x2, y2 = self.p2
        steps = int(math.hypot(x2 - x1, y2 - y1) // 18)
        for i in range(steps + 1):
            t = i / max(1, steps)
            zx, zy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            pygame.draw.rect(
                surf, (195, 200, 210), (zx - 8, zy - 4, 16, 8), border_radius=2
            )

        # Плечи и голова человека сверху
        sway = math.sin(self.step) * 2.5
        pygame.draw.circle(
            surf, (0, 0, 0, 90), (int(self.x + 2), int(self.y + 3)), 8
        )
        pygame.draw.ellipse(
            surf, self.shirt, (self.x - 8, self.y - 5 + sway * 0.3, 16, 10)
        )
        pygame.draw.circle(
            surf, (240, 205, 175), (int(self.x), int(self.y)), 5
        )


class BarrierGate:

    def __init__(self, bx, by, length, horizontal=True):
        self.bx, self.by = bx, by
        self.length = length
        self.horizontal = horizontal
        self.open_progress = 0.0  # 0.0 закрыт, 1.0 открыт

    def update(self, player):
        cx = self.bx + (self.length / 2 if self.horizontal else 0)
        cy = self.by + (0 if self.horizontal else self.length / 2)
        near = math.hypot(player.x - cx, player.y - cy) < 105
        if near:
            self.open_progress = min(1.0, self.open_progress + 0.035)
        else:
            self.open_progress = max(0.0, self.open_progress - 0.02)

    def get_vertices(self):
        if self.open_progress > 0.78:
            return None
        cur_len = self.length * (1.0 - self.open_progress)
        if self.horizontal:
            return [
                (self.bx, self.by - 4),
                (self.bx + cur_len, self.by - 4),
                (self.bx + cur_len, self.by + 4),
                (self.bx, self.by + 4),
            ]
        return [
            (self.bx - 4, self.by),
            (self.bx + 4, self.by),
            (self.bx + 4, self.by + cur_len),
            (self.bx - 4, self.by + cur_len),
        ]

    def draw(self, surf):
        # Тумба шлагбаума со светодиодом
        pygame.draw.rect(
            surf, (55, 60, 70), (self.bx - 9, self.by - 9, 18, 18), border_radius=4
        )
        led = (50, 235, 90) if self.open_progress > 0.78 else (245, 55, 55)
        pygame.draw.circle(surf, led, (self.bx, self.by), 4)

        cur_len = int(self.length * (1.0 - self.open_progress * 0.88))
        if cur_len > 6:
            for i in range(0, cur_len, 14):
                col = (230, 45, 45) if (i // 14) % 2 == 0 else (245, 245, 250)
                seg = min(14, cur_len - i)
                if self.horizontal:
                    pygame.draw.rect(surf, col, (self.bx + i, self.by - 3, seg, 6))
                else:
                    pygame.draw.rect(surf, col, (self.bx - 3, self.by + i, 6, seg))


# Секретный обитатель парковки :)
class ParkingMascot:

    def __init__(self, spot_x, spot_y):
        self.x, self.y = float(spot_x), float(spot_y)
        self.vx = self.vy = 0.0
        self.state = "SLEEP"  # SLEEP, STARTLED, RUN, SIT
        self.timer = 0
        self.bubble = ""
        self.tail_phase = 0.0

    def update(self, player):
        self.tail_phase += 0.14
        dist = math.hypot(player.x - self.x, player.y - self.y)
        if player.trailer:
            dist = min(
                dist,
                math.hypot(player.trailer.x - self.x, player.trailer.y - self.y),
            )

        keys = pygame.key.get_pressed()
        honk = keys[pygame.K_h]

        if self.state == "SLEEP":
            if dist < 155 or (honk and dist < 280):
                self.state = "STARTLED"
                self.timer = 22
                self.bubble = "МЯУ?!"
                sfx.play(sfx.beep_hi)
        elif self.state == "STARTLED":
            self.timer -= 1
            if self.timer <= 0:
                self.state = "RUN"
                ang = math.atan2(self.y - player.y, self.x - player.x) + random.uniform(
                    -0.5, 0.5
                )
                self.vx = math.cos(ang) * 3.8
                self.vy = math.sin(ang) * 3.8
                self.timer = 44
                self.bubble = "Тык-дык!"
        elif self.state == "RUN":
            self.x = max(55, min(WIDTH - 55, self.x + self.vx))
            self.y = max(85, min(HEIGHT - 115, self.y + self.vy))
            self.timer -= 1
            if self.timer <= 0:
                self.state = "SIT"
                self.bubble = ""
        elif self.state == "SIT":
            if dist < 75:
                self.state = "STARTLED"
                self.timer = 14
                self.bubble = "Шшш!"

    def draw(self, surf, is_won, ticks):
        x, y = int(self.x), int(self.y)
        orange = (240, 145, 45)
        dark_o = (195, 100, 25)

        if self.state == "SLEEP":
            # Свернулся калачиком прямо на тёплом парковочном месте!
            pygame.draw.circle(surf, (0, 0, 0, 80), (x + 2, y + 3), 11)
            pygame.draw.circle(surf, orange, (x, y), 10)
            pygame.draw.arc(
                surf, dark_o, (x - 8, y - 8, 16, 16), 0.4, 2.8, 2
            )
            # Ушки
            pygame.draw.polygon(
                surf, orange, [(x - 7, y - 4), (x - 10, y - 11), (x - 3, y - 8)]
            )
            pygame.draw.polygon(
                surf, orange, [(x + 1, y - 8), (x + 5, y - 12), (x + 6, y - 5)]
            )
            # Плавающие буквы Zzz...
            z_off = int((ticks * 0.03) % 18)
            zt = font_xs.render("Zzz...", True, (255, 245, 190))
            surf.blit(zt, (x + 10, y - 16 - z_off))
        else:
            # Хвостик виляет
            tw = math.sin(self.tail_phase) * 6
            pygame.draw.line(
                surf, dark_o, (x, y + 6), (x + int(tw), y + 16), 3
            )
            # Тело и голова рыжего кота
            jump = -7 if self.state == "STARTLED" else 0
            pygame.draw.ellipse(
                surf, orange, (x - 8, y - 4 + jump, 16, 14)
            )
            pygame.draw.circle(surf, orange, (x, y - 7 + jump), 7)
            pygame.draw.polygon(
                surf,
                dark_o,
                [(x - 6, y - 10 + jump), (x - 8, y - 17 + jump), (x - 1, y - 13 + jump)],
            )
            pygame.draw.polygon(
                surf,
                dark_o,
                [(x + 6, y - 10 + jump), (x + 8, y - 17 + jump), (x + 1, y - 13 + jump)],
            )
            # Глазки
            pygame.draw.circle(surf, (35, 220, 80), (x - 3, y - 8 + jump), 2)
            pygame.draw.circle(surf, (35, 220, 80), (x + 3, y - 8 + jump), 2)

            msg = "Мурр! 10/10 ★" if is_won else self.bubble
            if msg:
                bt = font_xs.render(msg, True, (255, 255, 255))
                bw = bt.get_width() + 10
                pygame.draw.rect(
                    surf,
                    (25, 28, 36),
                    (x - bw // 2, y - 34 + jump, bw, 18),
                    border_radius=6,
                )
                pygame.draw.rect(
                    surf,
                    orange,
                    (x - bw // 2, y - 34 + jump, bw, 18),
                    1,
                    border_radius=6,
                )
                surf.blit(bt, (x - bt.get_width() // 2, y - 33 + jump))


# ==========================================
# 6. СПИСОК МИССИЙ (8 РАЗНООБРАЗНЫХ УРОВНЕЙ)
# ==========================================
LEVELS = [
    {
        "name": "1. Солнечный двор",
        "hint": "Разминка! Обрати внимание, кто греется на твоём месте :)",
        "weather": "clear",
        "night": False,
        "trailer": False,
        "start": (140, 520, 0),
        "target": (880, 200, 96, 48, 0),
        "curbs": [(440, 330, 250, 55)],
        "cars": [(880, 135, 180, (70, 120, 200)), (880, 265, 0, (140, 145, 155))],
        "traffic": [],
        "peds": [(360, 140, 360, 540)],
        "gates": [],
    },
    {
        "name": "2. Оживлённый проспект",
        "hint": "Пропусти поток машин и аккуратно встань параллельно бордюру",
        "weather": "clear",
        "night": False,
        "trailer": False,
        "start": (150, 480, 0),
        "target": (620, 130, 96, 46, 0),
        "curbs": [(180, 390, 760, 40)],
        "cars": [
            (500, 130, 0, (220, 165, 40)),
            (740, 130, 0, (60, 160, 100)),
            (380, 130, 0, (135, 80, 170)),
        ],
        "traffic": [
            (-60, 265, WIDTH + 80, 265, 2.7, (200, 65, 65)),
            (WIDTH + 80, 325, -60, 325, 2.4, (65, 145, 215)),
        ],
        "peds": [],
        "gates": [],
    },
    {
        "name": "3. Платный КПП со шлагбаумом",
        "hint": "Подъедь вплотную к шлагбауму, дождись открытия и паркуйся задом",
        "weather": "clear",
        "night": False,
        "trailer": False,
        "start": (140, 210, 0),
        "target": (920, 515, 96, 48, 180),
        "curbs": [(520, 68, 36, 200), (520, 385, 36, 268)],
        "cars": [
            (920, 450, 180, (80, 145, 155)),
            (920, 580, 180, (185, 95, 55)),
        ],
        "traffic": [],
        "peds": [(670, 140, 670, 560)],
        "gates": [(538, 272, 110, False)],
    },
    {
        "name": "4. Осенний ливень",
        "hint": "Мокрый асфальт увеличивает тормозной путь! Включаются дворники",
        "weather": "rain",
        "night": False,
        "trailer": False,
        "start": (150, 535, 0),
        "target": (660, 210, 96, 48, -45),
        "curbs": [(280, 405, 590, 38)],
        "cars": [
            (565, 210, -45, (195, 55, 120)),
            (755, 210, -45, (55, 165, 135)),
            (850, 210, -45, (110, 120, 200)),
        ],
        "traffic": [(-60, 335, WIDTH + 80, 335, 2.5, (215, 180, 50))],
        "peds": [],
        "gates": [],
    },
    {
        "name": "5. Дачник с ПРИЦЕПОМ",
        "hint": "Завези ПРИЦЕП в зеленую зону! Сначала просто проедь сквозь карман вперед",
        "weather": "clear",
        "night": False,
        "trailer": True,
        "start": (190, 350, 0),
        "target": (760, 350, 86, 48, 0),
        "curbs": [(420, 175, 280, 40), (420, 485, 280, 40)],
        "cars": [
            (760, 210, 0, (90, 135, 195)),
            (760, 490, 180, (195, 85, 75)),
        ],
        "traffic": [],
        "peds": [],
        "gates": [],
    },
    {
        "name": "6. Зимний гололёд",
        "hint": "Очень скользкий лёд! Отпускай газ заранее и лови занос",
        "weather": "ice",
        "night": False,
        "trailer": False,
        "start": (140, 155, 0),
        "target": (940, 515, 96, 48, -90),
        "curbs": [(340, 68, 38, 340), (670, 255, 38, 398)],
        "cars": [
            (870, 515, -90, (215, 175, 55)),
            (1010, 515, -90, (90, 170, 100)),
            (505, 175, 0, (165, 80, 85)),
        ],
        "traffic": [],
        "peds": [(505, 280, 505, 560)],
        "gates": [],
    },
    {
        "name": "7. Высший пилотаж: Прицеп ЗАДОМ",
        "hint": "Классика автошколы: затолкай прицеп задним ходом (S) в широкий бокс!",
        "weather": "clear",
        "night": False,
        "trailer": True,
        "start": (350, 360, 0),
        "target": (880, 360, 92, 60, 0),
        "curbs": [(660, 150, 40, 145), (660, 425, 40, 145)],
        "cars": [
            (880, 260, 180, (75, 130, 190)),
            (880, 460, 180, (180, 110, 65)),
        ],
        "traffic": [],
        "peds": [],
        "gates": [],
    },
    {
        "name": "8. Ночной ливень в мегаполисе (ФИНАЛ)",
        "hint": "Тьма, дождь, шлагбаум и плотный трафик. Докажи свой класс!",
        "weather": "rain",
        "night": True,
        "trailer": False,
        "start": (135, 540, 0),
        "target": (925, 180, 96, 48, 135),
        "curbs": [(340, 290, 380, 38), (340, 328, 38, 175)],
        "cars": [
            (835, 180, 135, (65, 95, 165)),
            (1015, 180, 135, (165, 65, 95)),
            (540, 475, 0, (85, 155, 115)),
        ],
        "traffic": [(WIDTH + 80, 225, -60, 225, 2.8, (220, 75, 75))],
        "peds": [(240, 140, 240, 420)],
        "gates": [(340, 170, 115, False)],
    },
]


# ==========================================
# 7. РЕНДЕР КАРТЫ, ПОГОДЫ, ГАРАЖА И ПРИБОРОВ
# ==========================================
def build_surface_bg(weather):
    bg = pygame.Surface((WIDTH, HEIGHT))
    if weather == "ice":
        bg.fill((175, 198, 218))
        for _ in range(9000):
            x, y = random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1)
            c = random.randint(185, 225)
            bg.set_at((x, y), (c - 15, c - 4, min(255, c + 12)))
    else:
        base = 28 if weather == "rain" else 38
        bg.fill((base, base + 2, base + 8))
        for _ in range(12000):
            x, y = random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1)
            c = random.randint(base - 6, base + 12)
            bg.set_at((x, y), (c, c, c + 5))
        if weather == "rain":
            # Глянцевые лужи на мокром асфальте
            puddle = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for px, py, pw, ph in [
                (260, 210, 130, 55),
                (620, 470, 160, 65),
                (790, 290, 115, 48),
            ]:
                pygame.draw.ellipse(puddle, (65, 85, 115, 75), (px, py, pw, ph))
                pygame.draw.ellipse(
                    puddle, (110, 140, 175, 45), (px + 14, py + 10, pw - 28, ph - 22)
                )
            bg.blit(puddle, (0, 0))
    return bg


def draw_curb_3d(surf, rect, weather):
    x, y, w, h = rect
    pygame.draw.rect(surf, (88, 92, 102), rect, border_radius=4)
    step = 24
    c1 = (80, 145, 215) if weather == "ice" else (210, 45, 45)
    c2 = (238, 240, 245)
    for i in range(0, w, step):
        col = c1 if (i // step) % 2 == 0 else c2
        pygame.draw.rect(surf, col, (x + i, y, min(step, w - i), 5))
        pygame.draw.rect(surf, col, (x + i, y + h - 5, min(step, w - i), 5))
    for j in range(0, h, step):
        col = c1 if (j // step) % 2 == 0 else c2
        pygame.draw.rect(surf, col, (x, y + j, 5, min(step, h - j)))
        pygame.draw.rect(surf, col, (x + w - 5, y + j, 5, min(step, h - j)))


def check_box_fit(verts, target_Angle_Check, entity_angle, target_data):
    tx, ty, tw, th, tang = target_data
    rad = math.radians(-tang)
    ca, sa = math.cos(rad), math.sin(rad)
    hw, hh = tw / 2, th / 2
    for vx, vy in verts:
        dx, dy = vx - tx, vy - ty
        lx, ly = dx * ca - dy * sa, dx * sa + dy * ca
        if not (-hw <= lx <= hw and -hh <= ly <= hh):
            return False, False
    if not target_Angle_Check:
        return True, True
    diff = abs((entity_angle - tang + 180) % 360 - 180)
    return True, (diff <= 28)


def draw_target_zone(surf, target_data, is_in, ang_ok, trailer_mode, ticks):
    tx, ty, tw, th, tang = target_data
    pulse = int(math.sin(ticks * 0.008) * 35)
    col = (
        (45, 245, 105)
        if (is_in and ang_ok)
        else ((255, 145, 35) if is_in else (255, min(255, 200 + pulse), 35))
    )

    s = pygame.Surface((tw + 14, th + 14), pygame.SRCALPHA)
    pygame.draw.rect(s, (*col, 55), (7, 7, tw, th), border_radius=6)
    pygame.draw.rect(s, (*col, 230), (7, 7, tw, th), 3, border_radius=6)

    cx, cy = 7 + tw // 2, 7 + th // 2
    if trailer_mode:
        lbl = font_xs.render("ПРИЦЕП", True, col)
        s.blit(lbl, (cx - lbl.get_width() // 2, cy - 8))
    else:
        pygame.draw.line(s, (*col, 215), (cx - 22, cy), (cx + 18, cy), 4)
        pygame.draw.polygon(
            s, (*col, 235), [(cx + 26, cy), (cx + 12, cy - 9), (cx + 12, cy + 9)]
        )

    rot = pygame.transform.rotate(s, -tang)
    surf.blit(rot, rot.get_rect(center=(tx, ty)).topleft)


def draw_hud(surf, player, lvl_idx, stars_total, timer_sec, sensors_on):
    top = pygame.Surface((WIDTH, 48), pygame.SRCALPHA)
    top.fill((14, 16, 22, 225))
    surf.blit(top, (0, 0))

    lvl = LEVELS[lvl_idx]
    t_name = font_md.render(lvl["name"], True, (245, 245, 250))
    t_hint = font_xs.render(lvl["hint"], True, (180, 200, 225))
    surf.blit(t_name, (24, 9))
    surf.blit(t_hint, (36 + t_name.get_width(), 16))

    st_txt = font_md.render(f"★ {stars_total}", True, (255, 210, 45))
    surf.blit(st_txt, (WIDTH - st_txt.get_width() - 25, 9))

    # Нижняя приборка
    dash = pygame.Surface((WIDTH, 68), pygame.SRCALPHA)
    dash.fill((14, 16, 22, 235))
    pygame.draw.line(dash, (60, 68, 84), (0, 0), (WIDTH, 0), 2)
    surf.blit(dash, (0, HEIGHT - 68))

    # Передача
    if player.braking:
        g, gc = "BRAKE", (245, 55, 55)
    elif player.speed > 0.08:
        g, gc = "D", (50, 230, 105)
    elif player.speed < -0.08:
        g, gc = "R", (255, 180, 40)
    else:
        g, gc = "N", (175, 180, 190)

    pygame.draw.rect(
        surf, (28, 32, 40), (22, HEIGHT - 55, 78, 42), border_radius=8
    )
    pygame.draw.rect(surf, gc, (22, HEIGHT - 55, 78, 42), 2, border_radius=8)
    gt = font_md.render(g, True, gc)
    surf.blit(gt, (22 + 39 - gt.get_width() // 2, HEIGHT - 49))

    # Спидометр
    kmh = int(abs(player.speed) * 17)
    surf.blit(
        font_md.render(f"{kmh:02d} км/ч", True, (240, 242, 248)),
        (116, HEIGHT - 54),
    )
    pygame.draw.rect(
        surf, (38, 42, 52), (116, HEIGHT - 23, 115, 7), border_radius=3
    )
    fw = int(min(1.0, abs(player.speed) / player.max_speed) * 115)
    if fw > 0:
        pygame.draw.rect(
            surf, (55, 170, 250), (116, HEIGHT - 23, fw, 7), border_radius=3
        )

    # Индикатор прочности кузова (3 сердечка / щита)
    surf.blit(
        font_xs.render("КУЗОВ:", True, (170, 175, 190)), (250, HEIGHT - 53)
    )
    for i in range(3):
        hc = (50, 225, 100) if i < player.hp else (55, 58, 68)
        if player.hp == 1 and i == 0:
            hc = (245, 60, 60)
        pygame.draw.rect(
            surf, hc, (250 + i * 26, HEIGHT - 32, 20, 12), border_radius=3
        )

    # Парктроник (расстояние в метрах)
    min_d = min(player.sensor_front, player.sensor_rear)
    p_str = (
        f"РАДАР: {min_d / 28:.1f} м"
        if (sensors_on and min_d < 90)
        else ("РАДАР: ОК" if sensors_on else "РАДАР: ВЫКЛ")
    )
    p_col = (
        (255, 65, 65)
        if min_d < 22
        else ((255, 200, 45) if min_d < 45 else (120, 220, 150))
    )
    surf.blit(
        font_sm.render(p_str, True, p_col if sensors_on else (110, 115, 125)),
        (348, HEIGHT - 52),
    )
    surf.blit(
        font_xs.render(f"ВРЕМЯ: {timer_sec:.1f} с", True, (205, 210, 225)),
        (348, HEIGHT - 28),
    )

    # Хоткеи
    hk = font_xs.render(
        "[G] ГАРАЖ авто   |   [T] Радар   |   [H] Гудок   |   [R] Рестарт   |   [N/P] Уровни",
        True,
        (235, 200, 95),
    )
    surf.blit(hk, (WIDTH - hk.get_width() - 22, HEIGHT - 44))


def draw_garage_overlay(surf, selected_idx, total_stars):
    ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    ov.fill((10, 12, 18, 225))
    surf.blit(ov, (0, 0))

    title = font_lg.render("ГАРАЖ АВТОПАРКА", True, (255, 215, 55))
    sub = font_sm.render(
        f"Твои звёзды: ★ {total_stars}   |   Выбирай стрелками [ A / D ] или [ 1 - 4 ]   |   [ ENTER / G ] — Выехать!",
        True,
        (205, 215, 230),
    )
    surf.blit(title, (WIDTH // 2 - title.get_width() // 2, 70))
    surf.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 128))

    card_w, card_h = 240, 340
    gap = 24
    start_x = (WIDTH - (card_w * 4 + gap * 3)) // 2

    for i, sp in enumerate(CAR_SPECS):
        cx = start_x + i * (card_w + gap)
        cy = 195
        unlocked = total_stars >= sp["unlock_stars"]
        is_sel = i == selected_idx

        bg_c = (32, 38, 52) if is_sel else (22, 25, 34)
        bd_c = (
            (55, 235, 115)
            if (is_sel and unlocked)
            else ((245, 80, 80) if is_sel else (65, 72, 88))
        )
        pygame.draw.rect(surf, bg_c, (cx, cy, card_w, card_h), border_radius=14)
        pygame.draw.rect(
            surf, bd_c, (cx, cy, card_w, card_h), 3 if is_sel else 1, border_radius=14
        )

        # Превью машины
        preview = create_car_body_surface(
            sp["w"], sp["h"], sp["color"], sp["stripes"]
        )
        big_p = pygame.transform.smoothscale(
            preview, (int(preview.get_width() * 1.45), int(preview.get_height() * 1.45))
        )
        surf.blit(
            big_p,
            (cx + card_w // 2 - big_p.get_width() // 2, cy + 62 - big_p.get_height() // 2),
        )

        nm = font_md.render(sp["name"], True, (245, 245, 250))
        surf.blit(nm, (cx + card_w // 2 - nm.get_width() // 2, cy + 115))

        # Полоски характеристик
        stats = [
            ("Скорость", sp["max_spd"] / 5.5),
            ("Поворот", sp["steer"] / 40.0),
            ("Занос", max(0.08, sp["drift"])),
        ]
        for si, (st_lbl, val) in enumerate(stats):
            sy = cy + 162 + si * 34
            surf.blit(font_xs.render(st_lbl, True, (175, 185, 200)), (cx + 18, sy))
            pygame.draw.rect(
                surf, (45, 50, 62), (cx + 95, sy + 4, 125, 9), border_radius=4
            )
            pygame.draw.rect(
                surf,
                (65, 175, 250),
                (cx + 95, sy + 4, int(125 * min(1.0, val)), 9),
                border_radius=4,
            )

        # Статус открытия
        if unlocked:
            st = font_sm.render(
                "ВЫБРАНО" if is_sel else f"Нажми [{i + 1}]",
                True,
                (70, 235, 120) if is_sel else (160, 170, 185),
            )
        else:
            st = font_sm.render(
                f"Нужно ★ {sp['unlock_stars']}", True, (255, 110, 90)
            )
        surf.blit(st, (cx + card_w // 2 - st.get_width() // 2, cy + 292))


# ==========================================
# 8. ОСНОВНОЙ ИГРОВОЙ ЦИКЛ
# ==========================================
def main():
    skidmarks = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    current_lvl = 0
    car_idx = 1  # По умолчанию Спорткар GT
    best_stars = {}
    sensors_on = True

    player = PlayerCar(CAR_SPECS[car_idx])
    bg_surf = None
    curbs, parked_cars, traffic_cars, peds, gates, particles = [], [], [], [], [], []
    rain_drops = [
        [random.randint(0, WIDTH), random.randint(0, HEIGHT)] for _ in range(110)
    ]
    mascot = None

    state = "PLAYING"  # PLAYING, GARAGE, CRASHED, WON, COMPLETED
    shake = 0
    lvl_ticks = 0

    def load_level(idx):
        nonlocal bg_surf, curbs, parked_cars, traffic_cars, peds, gates, mascot, state, lvl_ticks
        skidmarks.fill((0, 0, 0, 0))
        particles.clear()
        lvl = LEVELS[idx]
        bg_surf = build_surface_bg(lvl["weather"])
        player.apply_spec(CAR_SPECS[car_idx])
        player.reset(*lvl["start"], with_trailer=lvl["trailer"])

        curbs = [
            pygame.Rect(0, 48, WIDTH, 18),
            pygame.Rect(0, HEIGHT - 86, WIDTH, 18),
            pygame.Rect(0, 48, 18, HEIGHT - 134),
            pygame.Rect(WIDTH - 18, 48, 18, HEIGHT - 134),
        ] + [pygame.Rect(*c) for c in lvl["curbs"]]

        parked_cars = [ParkedCar(*c) for c in lvl["cars"]]
        traffic_cars = [TrafficCar(*t) for t in lvl["traffic"]]
        peds = [Pedestrian(*p) for p in lvl["peds"]]
        gates = [BarrierGate(*g) for g in lvl["gates"]]

        tx, ty, _, _, _ = lvl["target"]
        mascot = ParkingMascot(tx, ty)
        state = "PLAYING"
        lvl_ticks = 0

    load_level(current_lvl)

    while True:
        clock.tick(60)
        ticks = pygame.time.get_ticks()
        total_stars = sum(best_stars.values())

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if state == "GARAGE":
                    if event.key in (pygame.K_a, pygame.K_LEFT):
                        car_idx = (car_idx - 1) % len(CAR_SPECS)
                    elif event.key in (pygame.K_d, pygame.K_RIGHT):
                        car_idx = (car_idx + 1) % len(CAR_SPECS)
                    elif event.key in (
                        pygame.K_1,
                        pygame.K_2,
                        pygame.K_3,
                        pygame.K_4,
                    ):
                        idx_try = event.key - pygame.K_1
                        if total_stars >= CAR_SPECS[idx_try]["unlock_stars"]:
                            car_idx = idx_try
                            load_level(current_lvl)
                    elif event.key in (
                        pygame.K_RETURN,
                        pygame.K_g,
                        pygame.K_ESCAPE,
                    ):
                        if total_stars >= CAR_SPECS[car_idx]["unlock_stars"]:
                            load_level(current_lvl)
                    continue

                if event.key == pygame.K_g:
                    sfx.stop_engine()
                    state = "GARAGE"
                elif event.key == pygame.K_t:
                    sensors_on = not sensors_on
                elif event.key == pygame.K_h:
                    sfx.play(sfx.horn)
                elif event.key == pygame.K_r:
                    load_level(current_lvl)
                elif event.key == pygame.K_n:
                    current_lvl = (current_lvl + 1) % len(LEVELS)
                    load_level(current_lvl)
                elif event.key == pygame.K_p:
                    current_lvl = (current_lvl - 1) % len(LEVELS)
                    load_level(current_lvl)
                elif event.key == pygame.K_RETURN:
                    if state == "WON":
                        if current_lvl + 1 < len(LEVELS):
                            current_lvl += 1
                            load_level(current_lvl)
                        else:
                            state = "COMPLETED"
                    elif state == "COMPLETED":
                        current_lvl = 0
                        load_level(current_lvl)

        lvl = LEVELS[current_lvl]
        if player.trailer:
            is_in, ang_ok = check_box_fit(
                player.trailer.get_vertices(),
                False,
                player.trailer.angle,
                lvl["target"],
            )
        else:
            is_in, ang_ok = check_box_fit(
                player.get_vertices(), True, player.angle, lvl["target"]
            )

        if state == "PLAYING":
            lvl_ticks += 1
            player.update(lvl["weather"], particles, skidmarks, ticks)
            for tc in traffic_cars:
                tc.update(player)
            for pd in peds:
                pd.update(player)
            for gt in gates:
                gt.update(player)
            mascot.update(player)

            # Собираем все полигоны препятствий для коллизий и парктроника
            obs_polys = []
            for cr in curbs:
                obs_polys.append([
                    (cr.left, cr.top),
                    (cr.right, cr.top),
                    (cr.right, cr.bottom),
                    (cr.left, cr.bottom),
                ])
            for pc in parked_cars:
                obs_polys.append(pc.verts)
            for tc in traffic_cars:
                obs_polys.append(tc.get_vertices())
            for pd in peds:
                obs_polys.append(pd.get_vertices())
            for gt in gates:
                gv = gt.get_vertices()
                if gv:
                    obs_polys.append(gv)

            player.update_sensors(obs_polys, sensors_on, ticks)

            # Проверка ударов (машина + прицеп)
            p_verts = player.get_vertices()
            t_verts = player.trailer.get_vertices() if player.trailer else None
            hit = False
            for poly in obs_polys:
                if check_sat_collision(p_verts, poly) or (
                    t_verts and check_sat_collision(t_verts, poly)
                ):
                    hit = True
                    break

            if hit:
                shake = 14
                dead = player.bounce_damage(particles)
                if dead:
                    sfx.stop_engine()
                    state = "CRASHED"

            # Проверка успешной парковки
            if is_in and ang_ok and abs(player.speed) < 0.06:
                sfx.stop_engine()
                sfx.play(sfx.win)
                state = "WON"
                sec = lvl_ticks / 60.0
                earned = 3 if (sec < 18 and player.hp == 3) else (2 if sec < 32 else 1)
                best_stars[current_lvl] = max(
                    best_stars.get(current_lvl, 0), earned
                )
                for _ in range(55):
                    a = random.uniform(0, math.pi * 2)
                    s = random.uniform(2, 7)
                    particles.append(
                        Particle(
                            player.x,
                            player.y,
                            math.cos(a) * s,
                            math.sin(a) * s,
                            random.choice([
                                (60, 250, 120),
                                (55, 195, 255),
                                (255, 215, 50),
                            ]),
                            4,
                            45,
                            -0.05,
                        )
                    )

        for pt in particles[:]:
            pt.update()
            if pt.life <= 0:
                particles.remove(pt)

        # --- ОТРИСОВКА КАДРА ---
        canvas = pygame.Surface((WIDTH, HEIGHT))
        canvas.blit(bg_surf, (0, 0))
        canvas.blit(skidmarks, (0, 0))

        draw_target_zone(
            canvas, lvl["target"], is_in, ang_ok, lvl["trailer"], ticks
        )

        for cr in curbs:
            draw_curb_3d(canvas, cr, lvl["weather"])
        for gt in gates:
            gt.draw(canvas)
        for pd in peds:
            pd.draw(canvas)
        for pc in parked_cars:
            pc.draw(canvas)
        for tc in traffic_cars:
            tc.draw(canvas)

        mascot.draw(canvas, state == "WON", ticks)
        player.draw(canvas, lvl["weather"], sensors_on, ticks)

        for pt in particles:
            pt.draw(canvas)

        # Анимация проливного дождя
        if lvl["weather"] == "rain":
            for rd in rain_drops:
                rd[0] -= 4
                rd[1] += 13
                if rd[1] > HEIGHT or rd[0] < 0:
                    rd[0] = random.randint(0, WIDTH + 180)
                    rd[1] = random.randint(-60, 0)
                pygame.draw.line(
                    canvas,
                    (155, 185, 225),
                    (rd[0], rd[1]),
                    (rd[0] - 3, rd[1] + 11),
                    1,
                )

        # Ночное освещение
        if lvl["night"]:
            nm = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            nm.fill((6, 10, 24, 180))
            rad = math.radians(player.angle)
            fx = int(player.x + math.cos(rad) * 115)
            fy = int(player.y + math.sin(rad) * 115)
            pygame.draw.circle(nm, (6, 10, 24, 45), (fx, fy), 150)
            pygame.draw.circle(
                nm, (6, 10, 24, 85), (int(player.x), int(player.y)), 90
            )
            tx, ty, _, _, _ = lvl["target"]
            pygame.draw.circle(nm, (6, 10, 24, 65), (tx, ty), 95)
            canvas.blit(nm, (0, 0))

        timer_sec = lvl_ticks / 60.0
        draw_hud(
            canvas,
            player,
            current_lvl,
            sum(best_stars.values()),
            timer_sec,
            sensors_on,
        )

        if state == "GARAGE":
            draw_garage_overlay(canvas, car_idx, sum(best_stars.values()))
        elif state in ("CRASHED", "WON", "COMPLETED"):
            ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            ov.fill((10, 12, 16, 185))
            canvas.blit(ov, (0, 0))
            box = pygame.Rect(WIDTH // 2 - 280, HEIGHT // 2 - 120, 560, 240)
            pygame.draw.rect(canvas, (24, 28, 36), box, border_radius=14)

            if state == "CRASHED":
                pygame.draw.rect(
                    canvas, (235, 55, 55), box, 3, border_radius=14
                )
                t1 = font_lg.render("МАШИНА РАЗБИТА!", True, (245, 65, 65))
                t2 = font_md.render(
                    "Кончился запас прочности кузова", True, (210, 215, 225)
                )
                t3 = font_sm.render(
                    "Нажми [ R ] для рестарта или [ G ] для смены авто",
                    True,
                    (255, 210, 60),
                )
            elif state == "WON":
                pygame.draw.rect(
                    canvas, (50, 230, 105), box, 3, border_radius=14
                )
                st_cnt = best_stars.get(current_lvl, 1)
                stars_str = "★ " * st_cnt + "☆ " * (3 - st_cnt)
                t1 = font_lg.render("МАСТЕР ПАРКОВКИ!", True, (55, 235, 110))
                t2 = font_md.render(
                    f"Время: {timer_sec:.1f} с  |  Кузов: {player.hp}/3  |  {stars_str}",
                    True,
                    (255, 215, 45),
                )
                t3 = font_sm.render(
                    "[ ENTER ] — Дальше   |   [ G ] — Заглянуть в Гараж",
                    True,
                    (220, 225, 235),
                )
            else:
                pygame.draw.rect(
                    canvas, (255, 205, 45), box, 3, border_radius=14
                )
                t1 = font_lg.render("КАМПАНИЯ ПРОЙДЕНА!", True, (255, 215, 50))
                t2 = font_md.render(
                    f"Собрано звёзд: ★ {sum(best_stars.values())} из {len(LEVELS) * 3}",
                    True,
                    (235, 240, 245),
                )
                t3 = font_sm.render(
                    "Нажми [ G ] чтобы протестировать Лимузин или [ ENTER ] заново",
                    True,
                    (170, 235, 175),
                )

            canvas.blit(t1, (WIDTH // 2 - t1.get_width() // 2, box.y + 30))
            canvas.blit(t2, (WIDTH // 2 - t2.get_width() // 2, box.y + 106))
            canvas.blit(t3, (WIDTH // 2 - t3.get_width() // 2, box.y + 174))

        ox = oy = 0
        if shake > 0:
            shake -= 1
            ox, oy = random.randint(-6, 6), random.randint(-6, 6)

        screen.fill((12, 12, 16))
        screen.blit(canvas, (ox, oy))
        pygame.display.flip()


if __name__ == "__main__":
    main()