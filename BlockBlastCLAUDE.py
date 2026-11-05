# -*- coding: utf-8 -*-
"""
Block Blast Lite — классический режим + «Энергия» (поворот фигур).
Зависимости: pygame  (pip install pygame)
Сборка в exe: pyinstaller --onefile --noconsole --name BlockBlastLite blockblast.py
"""
import json
import math
import os
import random
import sys
from array import array

import pygame

# ---------------------------------------------------------------- настройки
W, H = 520, 740
N = 8                      # размер поля
CELL = 52                  # размер клетки на поле
BX, BY = 52, 140           # левый верхний угол поля
TS = 26                    # размер клетки фигуры в лотке
LIFT = 90                  # на сколько фигура поднимается над курсором при перетаскивании
TRAY_Y, TRAY_H = 578, 120
ENERGY_MAX = 6             # линий нужно для одного заряда
MAX_CHARGES = 3
FPS = 60

BG_TOP = (22, 26, 50)
PANEL = (34, 40, 76)
EMPTY = (46, 54, 98)
TEXT = (235, 238, 255)
DIM = (140, 150, 195)
GOLD = (255, 205, 80)
CYAN = (80, 215, 255)

PALETTE = [(235, 87, 87), (246, 160, 60), (243, 213, 70), (96, 200, 100),
           (70, 170, 235), (140, 110, 235), (220, 100, 190)]

# ---------------------------------------------------------------- фигуры
BASE = [
    ["#"],
    ["##"], ["###"], ["####"], ["#####"],
    ["##", "##"], ["###", "###"], ["###", "###", "###"],
    ["#.", "##"],
    ["#..", "#..", "###"],
    ["#.", "#.", "##"], [".#", ".#", "##"],
    ["###", ".#."],
    [".##", "##."], ["##", ".##"],
    ["###", "#.."], ["###", "..#"],
]


def norm(cells):
    mr = min(r for r, c in cells)
    mc = min(c for r, c in cells)
    return tuple(sorted((r - mr, c - mc) for r, c in cells))


def rot(cells):  # поворот по часовой
    return norm([(c, -r) for r, c in cells])


def build_shapes():
    seen, out = set(), []
    for pat in BASE:
        cells = norm([(r, c) for r, row in enumerate(pat)
                      for c, ch in enumerate(row) if ch == "#"])
        for _ in range(4):
            if cells not in seen:
                seen.add(cells)
                n = len(cells)
                w = 1.2 if n <= 3 else 1.0 if n == 4 else 0.6 if n == 5 else 0.5 if n == 6 else 0.35
                out.append((cells, w))
            cells = rot(cells)
    return out


SHAPES = build_shapes()


class Piece:
    __slots__ = ("cells", "color", "w", "h")

    def __init__(self, cells, color):
        self.cells = cells
        self.color = color
        self.w = max(c for r, c in cells) + 1
        self.h = max(r for r, c in cells) + 1

    def rotated(self):
        return Piece(rot(self.cells), self.color)


def can_place(grid, cells, row, col):
    for r, c in cells:
        rr, cc = row + r, col + c
        if rr < 0 or cc < 0 or rr >= N or cc >= N or grid[rr][cc]:
            return False
    return True


def fits_anywhere(grid, cells):
    for r in range(N):
        for c in range(N):
            if can_place(grid, cells, r, c):
                return True
    return False


# ---------------------------------------------------------------- сохранение
def save_path():
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "BlockBlastLite")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        pass
    return os.path.join(folder, "save.json")


# ---------------------------------------------------------------- звук
def make_sound(notes, note_dur=0.07, vol=0.4):
    rate = 22050
    buf = array("h")
    for f in notes:
        n = int(rate * note_dur)
        for i in range(n):
            t = i / rate
            env = min(1.0, i / 120) * (1 - i / n) ** 1.5
            v = math.sin(2 * math.pi * f * t) + 0.3 * math.sin(4 * math.pi * f * t)
            buf.append(int(v * env * vol * 32767 / 1.3))
    return pygame.mixer.Sound(buffer=buf.tobytes())


SCALE = [262, 294, 330, 392, 440, 523, 587, 659, 784]


# ---------------------------------------------------------------- игра
class Game:
    def __init__(self):
        try:
            pygame.mixer.pre_init(22050, -16, 1, 512)
        except Exception:
            pass
        pygame.init()
        pygame.display.set_caption("Block Blast Lite")
        self.screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
        self.canvas = pygame.Surface((W, H))
        self.clock = pygame.time.Clock()
        self.fonts = {}
        self.ov = pygame.Surface((CELL - 4, CELL - 4), pygame.SRCALPHA)
        self.sounds = {}
        self.init_sounds()
        self.load()
        self.bg = self.build_bg()
        self.reset()

    # ---- ресурсы
    def init_sounds(self):
        try:
            self.sounds["place"] = make_sound([196], 0.09, 0.5)
            self.sounds["bad"] = make_sound([110], 0.1, 0.3)
            self.sounds["rot"] = make_sound([660, 880], 0.05, 0.35)
            self.sounds["charge"] = make_sound([523, 659, 784, 1047], 0.06, 0.4)
            self.sounds["perfect"] = make_sound([523, 659, 784, 1047, 1319, 1568], 0.08, 0.45)
            self.sounds["over"] = make_sound([392, 330, 262, 196], 0.18, 0.4)
            for k in range(7):
                self.sounds["clear%d" % k] = make_sound(SCALE[:min(3 + k, 9)], 0.065, 0.4)
        except Exception:
            self.sounds = {}

    def play(self, name):
        s = self.sounds.get(name)
        if s:
            try:
                s.play()
            except Exception:
                pass

    def font(self, size, bold=True):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("segoeui,arial,dejavusans", size, bold)
        return self.fonts[key]

    def text(self, surf, s, size, color, bold=True, **pos):
        img = self.font(size, bold).render(s, True, color)
        rect = img.get_rect(**pos)
        surf.blit(img, rect)
        return rect

    def build_bg(self):
        bg = pygame.Surface((W, H))
        for y in range(H):
            k = y / H
            pygame.draw.line(bg, (int(22 + 10 * k), int(26 + 8 * k), int(50 + 24 * k)), (0, y), (W, y))
        pygame.draw.rect(bg, PANEL, (BX - 8, BY - 8, CELL * N + 16, CELL * N + 16), border_radius=14)
        for r in range(N):
            for c in range(N):
                pygame.draw.rect(bg, EMPTY, (BX + c * CELL + 2, BY + r * CELL + 2, CELL - 4, CELL - 4),
                                 border_radius=7)
        for i in range(3):
            pygame.draw.rect(bg, (30, 36, 70), self.slot_rect(i), border_radius=12)
        return bg

    def load(self):
        self.data = {"best": 0, "best_combo": 0, "games": 0}
        try:
            with open(save_path(), "r", encoding="utf-8") as f:
                self.data.update(json.load(f))
        except Exception:
            pass

    def save(self):
        try:
            with open(save_path(), "w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except Exception:
            pass

    # ---- состояние
    def reset(self):
        self.grid = [[0] * N for _ in range(N)]
        self.score = 0
        self.shown = 0.0
        self.combo = 0
        self.miss = 0
        self.max_combo = 0
        self.energy = 0
        self.charges = 0
        self.tray = [None] * 3
        self.drag = None
        self.over = False
        self.over_timer = None
        self.over_age = 0.0
        self.new_record = False
        self.particles = []
        self.anims = []
        self.floats = []
        self.shake = 0.0
        self.tray = self.new_tray()

    def fill_ratio(self):
        return sum(1 for row in self.grid for v in row if v) / (N * N)

    def rand_piece(self):
        fill = self.fill_ratio()
        weights = [w * (0.3 if fill > 0.55 and len(cells) >= 5 else 1.0) for cells, w in SHAPES]
        cells = random.choices(SHAPES, weights)[0][0]
        return Piece(cells, random.randrange(len(PALETTE)))

    def new_tray(self):
        pcs = []
        for _ in range(40):
            pcs = [self.rand_piece() for _ in range(3)]
            if any(fits_anywhere(self.grid, p.cells) for p in pcs):
                break
        return pcs

    def any_move(self):
        for p in self.tray:
            if p is None:
                continue
            shapes = [p.cells]
            if self.charges > 0:
                q = p
                for _ in range(3):
                    q = q.rotated()
                    shapes.append(q.cells)
            for cells in shapes:
                if fits_anywhere(self.grid, cells):
                    return True
        return False

    # ---- геометрия
    def slot_rect(self, i):
        sw = CELL * N / 3
        return pygame.Rect(int(BX + i * sw) + 3, TRAY_Y, int(sw) - 6, TRAY_H)

    def tray_topleft(self, i, p):
        rc = self.slot_rect(i)
        return rc.centerx - p.w * TS / 2, rc.centery - p.h * TS / 2

    def drag_topleft(self, p, mouse):
        return mouse[0] - p.w * CELL / 2, mouse[1] - p.h * CELL / 2 - LIFT

    def snapped(self, p, mouse):
        px, py = self.drag_topleft(p, mouse)
        return round((py - BY) / CELL), round((px - BX) / CELL)

    # ---- эффекты
    def popup(self, s, x, y, color=TEXT, size=26, dur=0.9):
        self.floats.append({"s": s, "x": x, "y": y, "t": 0.0, "dur": dur, "color": color, "size": size})

    def burst(self, x, y, color):
        for _ in range(3):
            a = random.uniform(0, math.tau)
            v = random.uniform(60, 220)
            self.particles.append([x, y, math.cos(a) * v, math.sin(a) * v - 60,
                                   random.uniform(0.3, 0.7), color, random.randint(3, 6)])

    # ---- ход
    def place(self, i, row, col):
        p = self.tray[i]
        g = self.grid
        for r, c in p.cells:
            g[row + r][col + c] = p.color + 1
        self.score += len(p.cells)

        rows = [r for r in range(N) if all(g[r])]
        cols = [c for c in range(N) if all(g[r][c] for r in range(N))]
        cleared = {(r, c) for r in rows for c in range(N)} | {(r, c) for c in cols for r in range(N)}
        L = len(rows) + len(cols)

        if L:
            self.combo += 1
            self.miss = 0
            self.max_combo = max(self.max_combo, self.combo)
            pts = 10 * L * L * max(1, self.combo)
            self.score += pts
            cx = cy = 0
            for r, c in cleared:
                color = g[r][c] - 1
                self.anims.append([r, c, color, 0.0])
                g[r][c] = 0
                x, y = BX + c * CELL + CELL / 2, BY + r * CELL + CELL / 2
                cx += x
                cy += y
                self.burst(x, y, PALETTE[color])
            cx /= len(cleared)
            cy /= len(cleared)
            praise = {1: "", 2: "Здорово!", 3: "Супер!"}.get(L, "Невероятно!")
            self.popup("+%d" % pts, cx, cy, GOLD, 34 if L < 3 else 42)
            if praise:
                self.popup(praise, cx, cy - 38, TEXT, 26)
            if self.combo >= 2:
                self.popup("Комбо x%d" % self.combo, cx, cy + 36, (255, 140, 90), 26)
            self.shake = min(14.0, 3.0 + 2.5 * L)
            self.play("clear%d" % min(L - 1 + max(0, self.combo - 1), 6))

            self.energy += L
            gained = False
            while self.energy >= ENERGY_MAX:
                if self.charges < MAX_CHARGES:
                    self.charges += 1
                    self.energy -= ENERGY_MAX
                    gained = True
                else:
                    self.energy = ENERGY_MAX
                    break
            if gained:
                self.popup("Заряд +1", BX + CELL * N / 2, BY - 22, CYAN, 24, 1.2)
                self.play("charge")

            if not any(any(row) for row in g):
                self.score += 500
                self.popup("ИДЕАЛЬНО! +500", BX + CELL * N / 2, BY + CELL * N / 2 - 70, GOLD, 40, 1.6)
                self.shake = 16.0
                self.play("perfect")
        else:
            self.play("place")
            self.miss += 1
            if self.miss >= 3 and self.combo:
                if self.combo >= 2:
                    self.popup("Комбо потеряно", BX + CELL * N / 2, BY + CELL * N + 12, DIM, 22)
                self.combo = 0
                self.miss = 0

        self.tray[i] = None
        if all(t is None for t in self.tray):
            self.tray = self.new_tray()
        if not self.any_move():
            self.over_timer = 0.7

    def rotate_piece(self, i, mouse):
        p = self.tray[i]
        if p is None:
            return
        q = p.rotated()
        if q.cells == p.cells:
            return
        if self.charges <= 0:
            self.popup("Нужна энергия", mouse[0], mouse[1] - 20, DIM, 22, 0.8)
            self.play("bad")
            return
        self.charges -= 1
        self.tray[i] = q
        self.play("rot")

    def finish(self):
        self.over = True
        self.over_age = 0.0
        self.data["games"] += 1
        self.data["best_combo"] = max(self.data["best_combo"], self.max_combo)
        if self.score > self.data["best"]:
            self.data["best"] = self.score
            self.new_record = True
        self.save()
        self.play("over")

    # ---- ввод
    def slot_under(self, pos):
        for i in range(3):
            if self.slot_rect(i).collidepoint(pos) and self.tray[i] is not None:
                return i
        return None

    def handle(self, e):
        if e.type == pygame.QUIT:
            self.quit()
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.quit()
            elif self.over and e.key in (pygame.K_SPACE, pygame.K_RETURN):
                self.reset()
            elif not self.over and e.key == pygame.K_r and self.over_timer is None:
                i = self.drag if self.drag is not None else self.slot_under(pygame.mouse.get_pos())
                if i is not None:
                    self.rotate_piece(i, pygame.mouse.get_pos())
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if self.over:
                if self.over_age > 0.5:
                    self.reset()
                return
            if self.over_timer is not None:
                return
            if e.button == 1:
                i = self.slot_under(e.pos)
                if i is not None:
                    self.drag = i
            elif e.button == 3:
                i = self.drag if self.drag is not None else self.slot_under(e.pos)
                if i is not None:
                    self.rotate_piece(i, e.pos)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag is not None:
            i, self.drag = self.drag, None
            p = self.tray[i]
            if p is not None:
                row, col = self.snapped(p, e.pos)
                if can_place(self.grid, p.cells, row, col):
                    self.place(i, row, col)
                elif BY - 40 < e.pos[1] < BY + CELL * N:
                    self.play("bad")

    def quit(self):
        self.save()
        pygame.quit()
        sys.exit()

    # ---- обновление
    def update(self, dt):
        self.shown += (self.score - self.shown) * min(1.0, dt * 8)
        if abs(self.score - self.shown) < 1:
            self.shown = self.score
        self.shake = max(0.0, self.shake - dt * 40)
        for a in self.anims:
            a[3] += dt
        self.anims = [a for a in self.anims if a[3] < 0.35]
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 600 * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for f in self.floats:
            f["t"] += dt
        self.floats = [f for f in self.floats if f["t"] < f["dur"]]
        if self.over_timer is not None:
            self.over_timer -= dt
            if self.over_timer <= 0:
                self.over_timer = None
                self.drag = None
                self.finish()
        if self.over:
            self.over_age += dt

    # ---- отрисовка
    def draw_cell(self, surf, x, y, size, ci):
        c = PALETTE[ci]
        dark = tuple(int(v * 0.68) for v in c)
        light = tuple(min(255, int(v * 1.25) + 25) for v in c)
        rad = max(3, size // 6)
        pygame.draw.rect(surf, dark, (x, y, size, size), border_radius=rad)
        pygame.draw.rect(surf, c, (x + 2, y + 2, size - 4, size - 4), border_radius=rad)
        pygame.draw.rect(surf, light, (x + 5, y + 4, size - 10, max(3, size // 6)), border_radius=3)

    def draw_piece(self, surf, p, x, y, size):
        for r, c in p.cells:
            self.draw_cell(surf, x + c * size + 1, y + r * size + 1, size - 2, p.color)

    def draw_bolt(self, surf, x, y, filled):
        pts = [(6, 0), (0, 12), (5, 12), (3, 22), (13, 8), (8, 8), (11, 0)]
        pts = [(x + px, y + py) for px, py in pts]
        if filled:
            pygame.draw.polygon(surf, GOLD, pts)
        pygame.draw.polygon(surf, GOLD if filled else (80, 88, 130), pts, 2)

    def draw(self):
        s = self.canvas
        s.blit(self.bg, (0, 0))
        mouse = pygame.mouse.get_pos()
        best = max(self.data["best"], self.score)

        # шапка
        self.text(s, "СЧЁТ", 14, DIM, topleft=(BX, 12))
        self.text(s, str(int(round(self.shown))), 48, TEXT, topleft=(BX, 26))
        self.text(s, "РЕКОРД", 14, DIM, topright=(BX + CELL * N, 12))
        self.text(s, str(best), 30, GOLD, topright=(BX + CELL * N, 28))

        # энергия
        bar = pygame.Rect(BX, 92, 250, 14)
        pygame.draw.rect(s, (30, 36, 70), bar, border_radius=7)
        k = self.energy / ENERGY_MAX
        if k > 0:
            pygame.draw.rect(s, CYAN, (bar.x, bar.y, max(14, int(bar.w * k)), bar.h), border_radius=7)
        self.text(s, "ЭНЕРГИЯ", 12, DIM, midleft=(bar.right + 10, bar.centery))
        for i in range(MAX_CHARGES):
            self.draw_bolt(s, BX + CELL * N - 34 * (MAX_CHARGES - i) + 14, 86, i < self.charges)

        # комбо
        if self.combo >= 2:
            pulse = 1 + 0.08 * math.sin(pygame.time.get_ticks() / 120)
            self.text(s, "КОМБО x%d" % self.combo, int(20 * pulse), (255, 150, 90), midleft=(BX, 122))
            left = max(0, 3 - self.miss)
            for i in range(3):
                pygame.draw.circle(s, (255, 150, 90) if i < left else (70, 78, 120),
                                   (BX + 130 + i * 18, 122), 5)

        # поле
        for r in range(N):
            for c in range(N):
                v = self.grid[r][c]
                if v:
                    self.draw_cell(s, BX + c * CELL + 2, BY + r * CELL + 2, CELL - 4, v - 1)

        # подсказка при перетаскивании
        if self.drag is not None and self.tray[self.drag] is not None:
            p = self.tray[self.drag]
            row, col = self.snapped(p, mouse)
            if can_place(self.grid, p.cells, row, col):
                cellset = {(row + r, col + c) for r, c in p.cells}
                full_r = [r for r in range(N) if all(self.grid[r][c] or (r, c) in cellset for c in range(N))]
                full_c = [c for c in range(N) if all(self.grid[r][c] or (r, c) in cellset for r in range(N))]
                hl = {(r, c) for r in full_r for c in range(N)} | {(r, c) for c in full_c for r in range(N)}
                self.ov.fill((255, 255, 255, 70))
                for r, c in hl:
                    s.blit(self.ov, (BX + c * CELL + 2, BY + r * CELL + 2))
                col_rgb = PALETTE[p.color]
                self.ov.fill((*col_rgb, 150))
                for r, c in cellset:
                    s.blit(self.ov, (BX + c * CELL + 2, BY + r * CELL + 2))

        # анимация очистки
        for r, c, ci, t in self.anims:
            k = t / 0.35
            size = int((CELL - 4) * (1 - k))
            if size < 2:
                continue
            base = PALETTE[ci]
            w = max(0.0, 1 - k * 2)
            col = tuple(int(base[j] + (255 - base[j]) * w) for j in range(3))
            cx, cy = BX + c * CELL + CELL / 2, BY + r * CELL + CELL / 2
            pygame.draw.rect(s, col, (cx - size / 2, cy - size / 2, size, size), border_radius=max(3, size // 6))

        # лоток
        for i, p in enumerate(self.tray):
            if p is None or i == self.drag:
                continue
            x, y = self.tray_topleft(i, p)
            self.draw_piece(s, p, x, y, TS)

        # перетаскиваемая фигура
        if self.drag is not None and self.tray[self.drag] is not None:
            p = self.tray[self.drag]
            x, y = self.drag_topleft(p, mouse)
            self.draw_piece(s, p, x, y, CELL)

        # частицы
        for x, y, vx, vy, life, color, size in self.particles:
            pygame.draw.rect(s, color, (x, y, size, size), border_radius=2)

        # всплывающие тексты
        for f in self.floats:
            k = f["t"] / f["dur"]
            img = self.font(f["size"]).render(f["s"], True, f["color"])
            img.set_alpha(int(255 * min(1.0, (1 - k) * 2.2)))
            rect = img.get_rect(center=(f["x"], f["y"] - 45 * k))
            rect.clamp_ip(pygame.Rect(0, 0, W, H))
            s.blit(img, rect)

        # подсказка управления
        self.text(s, "ЛКМ — перетащить    ПКМ / R — повернуть (расходует заряд)", 14, DIM, False,
                  center=(W // 2, 718))

        # конец игры
        if self.over:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((10, 12, 28, 200))
            s.blit(shade, (0, 0))
            self.text(s, "ИГРА ОКОНЧЕНА", 44, TEXT, center=(W // 2, 240))
            self.text(s, str(self.score), 72, GOLD, center=(W // 2, 330))
            if self.new_record:
                self.text(s, "НОВЫЙ РЕКОРД!", 28, (255, 140, 90), center=(W // 2, 395))
            else:
                self.text(s, "Рекорд: %d" % self.data["best"], 24, DIM, center=(W // 2, 395))
            self.text(s, "Лучшее комбо: %d    Игр сыграно: %d" % (self.data["best_combo"], self.data["games"]),
                      18, DIM, False, center=(W // 2, 440))
            if int(pygame.time.get_ticks() / 500) % 2 == 0:
                self.text(s, "Клик или пробел — играть снова", 22, TEXT, center=(W // 2, 520))

        ox = oy = 0
        if self.shake > 0:
            ox = random.randint(-int(self.shake), int(self.shake))
            oy = random.randint(-int(self.shake), int(self.shake))
        self.screen.fill((0, 0, 0))
        self.screen.blit(s, (ox, oy))
        pygame.display.flip()

    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for e in pygame.event.get():
                self.handle(e)
            self.update(dt)
            self.draw()


if __name__ == "__main__":
    Game().run()