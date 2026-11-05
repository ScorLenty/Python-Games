import sys
import os
import json
import random
import math
import pygame

# --- Инициализация ---
pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

# --- Настройки экрана ---
WINDOW_WIDTH = 520
WINDOW_HEIGHT = 740
FPS = 60
GRID_SIZE = 8
CELL_SIZE = 48
GRID_OFFSET_X = (WINDOW_WIDTH - (GRID_SIZE * CELL_SIZE)) // 2
GRID_OFFSET_Y = 140

# --- Палитра цветов (Neon Modern) ---
COLOR_BG = (18, 18, 28)
COLOR_GRID_BG = (28, 28, 44)
COLOR_GRID_LINE = (38, 38, 58)
COLOR_TEXT = (240, 240, 250)
COLOR_TEXT_DIM = (140, 140, 160)
COLOR_GOLD = (255, 204, 0)
COLOR_ACCENT = (0, 230, 255)

BLOCK_PALETTES = [
    (255, 75, 75),  # Коралл / Красный
    (255, 155, 50),  # Оранжевый
    (255, 220, 60),  # Желтый
    (50, 215, 120),  # Изумрудный
    (50, 175, 255),  # Небесный
    (155, 85, 255),  # Фиолетовый
    (255, 90, 180),  # Розовый
]

# --- Формы фигур (Polyominoes) ---
SHAPES = [
    # 1x1, 2x2, 3x3
    ([[1]], 0),
    ([[1, 1], [1, 1]], 1),
    ([[1, 1, 1], [1, 1, 1], [1, 1, 1]], 0),
    # Линии 2, 3, 4, 5 (горизонт)
    ([[1, 1]], 2),
    ([[1, 1, 1]], 3),
    ([[1, 1, 1, 1]], 4),
    ([[1, 1, 1, 1, 1]], 5),
    # Линии (вертикаль)
    ([[1], [1]], 2),
    ([[1], [1], [1]], 3),
    ([[1], [1], [1], [1]], 4),
    ([[1], [1], [1], [1], [1]], 5),
    # Уголки L (2x2)
    ([[1, 0], [1, 1]], 1),
    ([[0, 1], [1, 1]], 1),
    ([[1, 1], [1, 0]], 1),
    ([[1, 1], [0, 1]], 1),
    # Уголки L (3x3)
    ([[1, 0, 0], [1, 0, 0], [1, 1, 1]], 6),
    ([[0, 0, 1], [0, 0, 1], [1, 1, 1]], 6),
    ([[1, 1, 1], [1, 0, 0], [1, 0, 0]], 6),
    ([[1, 1, 1], [0, 0, 1], [0, 0, 1]], 6),
    # Т-образные
    ([[1, 1, 1], [0, 1, 0]], 3),
    ([[0, 1, 0], [1, 1, 1]], 3),
    ([[1, 0], [1, 1], [1, 0]], 3),
    ([[0, 1], [1, 1], [0, 1]], 3),
]


# --- Процедурный генератор звука ---
def play_sound(freq_start, freq_end, duration=0.08, volume=0.25):
    try:
        sample_rate = 44100
        n_samples = int(sample_rate * duration)
        buf = bytearray()
        for i in range(n_samples):
            t = i / n_samples
            freq = freq_start + (freq_end - freq_start) * t
            val = int(math.sin(2.0 * math.pi * freq * (i / sample_rate)) * 127 * (1.0 - t))
            sample = max(-128, min(127, val))
            buf.extend([sample & 0xFF, sample & 0xFF])
        snd = pygame.mixer.Sound(buffer=bytes(buf))
        snd.set_volume(volume)
        snd.play()
    except Exception:
        pass


# --- Система Рекордов ---
SCORE_FILE = os.path.join(os.path.expanduser("~"), ".block_blast_record.json")


def load_high_score():
    if os.path.exists(SCORE_FILE):
        try:
            with open(SCORE_FILE, "r") as f:
                return json.load(f).get("high_score", 0)
        except Exception:
            return 0
    return 0


def save_high_score(score):
    try:
        with open(SCORE_FILE, "w") as f:
            json.dump({"high_score": score}, f)
    except Exception:
        pass


class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.vx = random.uniform(-4, 4)
        self.vy = random.uniform(-6, 2)
        self.size = random.uniform(4, 8)
        self.color = color
        self.alpha = 255
        self.gravity = 0.25

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.size = max(0, self.size - 0.15)
        self.alpha = max(0, self.alpha - 6)

    def draw(self, surface):
        if self.alpha > 0 and self.size > 0:
            surf = pygame.Surface((int(self.size * 2), int(self.size * 2)), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*self.color, int(self.alpha)), (int(self.size), int(self.size)), int(self.size))
            surface.blit(surf, (int(self.x - self.size), int(self.y - self.size)))


class FloatingText:
    def __init__(self, text, x, y, color, size=24):
        self.text = text
        self.x = x
        self.y = y
        self.color = color
        self.font = pygame.font.SysFont("Arial", size, bold=True)
        self.life = 60
        self.max_life = 60

    def update(self):
        self.y -= 1.2
        self.life -= 1

    def draw(self, surface):
        if self.life > 0:
            alpha = int((self.life / self.max_life) * 255)
            txt_surf = self.font.render(self.text, True, self.color)
            txt_surf.set_alpha(alpha)
            surface.blit(txt_surf, (self.x - txt_surf.get_width() // 2, self.y))


class BlockShape:
    def __init__(self, shape_def, color_idx):
        self.matrix = [row[:] for row in shape_def]
        self.rows = len(self.matrix)
        self.cols = len(self.matrix[0])
        self.color = BLOCK_PALETTES[color_idx % len(BLOCK_PALETTES)]
        self.base_x = 0
        self.base_y = 0
        self.drag_x = 0
        self.drag_y = 0
        self.is_dragging = False

    def get_width(self, cell_size):
        return self.cols * cell_size

    def get_height(self, cell_size):
        return self.rows * cell_size

    def draw(self, surface, x, y, cell_sz, alpha=255):
        for r in range(self.rows):
            for c in range(self.cols):
                if self.matrix[r][c]:
                    bx = x + c * cell_sz
                    by = y + r * cell_sz
                    rect = pygame.Rect(bx + 2, by + 2, cell_sz - 4, cell_sz - 4)

                    surf = pygame.Surface((cell_sz, cell_sz), pygame.SRCALPHA)
                    color_with_alpha = (*self.color, alpha)

                    # Закругленный блок с фаской
                    inner_rect = pygame.Rect(2, 2, cell_sz - 4, cell_sz - 4)
                    pygame.draw.rect(surf, color_with_alpha, inner_rect, border_radius=6)
                    # Блик сверху
                    pygame.draw.line(surf, (255, 255, 255, int(alpha * 0.4)), (5, 4), (cell_sz - 5, 4), 2)
                    surface.blit(surf, (bx, by))


class BlockBlastApp:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Block Blast: Overdrive")
        self.clock = pygame.time.Clock()

        self.font_big = pygame.font.SysFont("Arial", 36, bold=True)
        self.font_mid = pygame.font.SysFont("Arial", 22, bold=True)
        self.font_small = pygame.font.SysFont("Arial", 16)

        self.high_score = load_high_score()
        self.reset_game()

    def reset_game(self):
        self.grid = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.grid_colors = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.score = 0
        self.combo = 0
        self.available_shapes = [None, None, None]
        self.pocket_shape = None
        self.can_swap_pocket = True
        self.particles = []
        self.floating_texts = []
        self.screen_shake = 0
        self.game_over = False
        self.dragged_shape = None
        self.dragged_index = -1
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        self.refill_shapes()

    def refill_shapes(self):
        for i in range(3):
            shape_def, color_idx = random.choice(SHAPES)
            self.available_shapes[i] = BlockShape(shape_def, color_idx)
        self.update_shape_positions()

    def update_shape_positions(self):
        slot_w = WINDOW_WIDTH // 3
        slot_y = 575
        for i, shape in enumerate(self.available_shapes):
            if shape:
                w = shape.get_width(CELL_SIZE * 0.65)
                h = shape.get_height(CELL_SIZE * 0.65)
                shape.base_x = i * slot_w + (slot_w - w) // 2
                shape.base_y = slot_y + (100 - h) // 2

    def can_fit_shape(self, shape, grid_r, grid_c):
        for r in range(shape.rows):
            for c in range(shape.cols):
                if shape.matrix[r][c]:
                    target_r = grid_r + r
                    target_c = grid_c + c
                    if target_r < 0 or target_r >= GRID_SIZE or target_c < 0 or target_c >= GRID_SIZE:
                        return False
                    if self.grid[target_r][target_c] != 0:
                        return False
        return True

    def has_any_valid_moves(self):
        shapes_to_check = [s for s in self.available_shapes if s is not None]
        if self.pocket_shape:
            shapes_to_check.append(self.pocket_shape)

        for shape in shapes_to_check:
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    if self.can_fit_shape(shape, r, c):
                        return True
        return False

    def place_shape(self, shape, grid_r, grid_c):
        placed_blocks = 0
        for r in range(shape.rows):
            for c in range(shape.cols):
                if shape.matrix[r][c]:
                    self.grid[grid_r + r][grid_c + c] = 1
                    self.grid_colors[grid_r + r][grid_c + c] = shape.color
                    placed_blocks += 1

        self.score += placed_blocks * 10
        self.check_clears()
        play_sound(320, 480, 0.05, 0.2)

        if self.score > self.high_score:
            self.high_score = self.score
            save_high_score(self.high_score)

    def check_clears(self):
        full_rows = [r for r in range(GRID_SIZE) if all(self.grid[r][c] == 1 for c in range(GRID_SIZE))]
        full_cols = [c for c in range(GRID_SIZE) if all(self.grid[r][c] == 1 for r in range(GRID_SIZE))]

        lines_cleared = len(full_rows) + len(full_cols)

        if lines_cleared > 0:
            self.combo += 1
            combo_mult = self.combo if self.combo > 1 else 1
            overdrive_bonus = 3 if self.combo >= 3 else 1
            line_score = (lines_cleared * 100) * combo_mult * overdrive_bonus
            self.score += line_score

            self.screen_shake = min(15, 4 + lines_cleared * 2 + (self.combo * 2))

            # Создание частиц
            cleared_cells = set()
            for r in full_rows:
                for c in range(GRID_SIZE):
                    cleared_cells.add((r, c))
            for c in full_cols:
                for r in range(GRID_SIZE):
                    cleared_cells.add((r, c))

            for r, c in cleared_cells:
                color = self.grid_colors[r][c] or COLOR_ACCENT
                cx = GRID_OFFSET_X + c * CELL_SIZE + CELL_SIZE // 2
                cy = GRID_OFFSET_Y + r * CELL_SIZE + CELL_SIZE // 2
                for _ in range(6):
                    self.particles.append(Particle(cx, cy, color))
                self.grid[r][c] = 0
                self.grid_colors[r][c] = None

            # Звук и надписи
            base_freq = 400 + (self.combo * 70)
            play_sound(base_freq, base_freq + 300, 0.12, 0.35)

            txt = f"+{line_score}"
            if self.combo > 1:
                txt += f"  x{self.combo}!"
            if self.combo >= 3:
                txt += " OVERDRIVE!"
            self.floating_texts.append(FloatingText(txt, WINDOW_WIDTH // 2, GRID_OFFSET_Y + 180, COLOR_GOLD, 28))
        else:
            self.combo = 0

    def swap_pocket(self):
        """Перемещение активной или первой доступной фигуры в карман"""
        if not self.can_swap_pocket:
            return

        avail_indices = [i for i, s in enumerate(self.available_shapes) if s is not None]
        if not avail_indices and self.pocket_shape is None:
            return

        if self.pocket_shape is None and avail_indices:
            idx = avail_indices[0]
            self.pocket_shape = self.available_shapes[idx]
            self.available_shapes[idx] = None
        elif self.pocket_shape is not None and avail_indices:
            idx = avail_indices[0]
            temp = self.pocket_shape
            self.pocket_shape = self.available_shapes[idx]
            self.available_shapes[idx] = temp

        self.update_shape_positions()
        self.can_swap_pocket = False
        play_sound(260, 520, 0.08, 0.2)

    def run(self):
        running = True
        while running:
            # Тряска экрана
            shake_ox = random.randint(-self.screen_shake, self.screen_shake) if self.screen_shake > 0 else 0
            shake_oy = random.randint(-self.screen_shake, self.screen_shake) if self.screen_shake > 0 else 0
            if self.screen_shake > 0:
                self.screen_shake -= 1

            mouse_x, mouse_y = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r and self.game_over:
                        self.reset_game()
                    elif event.key == pygame.K_SPACE and not self.game_over:
                        self.swap_pocket()

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.game_over:
                        self.reset_game()
                        continue

                    # Клик по карману
                    pocket_rect = pygame.Rect(WINDOW_WIDTH - 90, 35, 75, 75)
                    if pocket_rect.collidepoint(mouse_x, mouse_y):
                        self.swap_pocket()
                        continue

                    # Проверка захвата доступной фигуры
                    for i, shape in enumerate(self.available_shapes):
                        if shape:
                            sw = shape.get_width(CELL_SIZE * 0.65)
                            sh = shape.get_height(CELL_SIZE * 0.65)
                            srect = pygame.Rect(shape.base_x, shape.base_y, sw, sh)
                            if srect.collidepoint(mouse_x, mouse_y):
                                self.dragged_shape = shape
                                self.dragged_index = i
                                shape.is_dragging = True
                                # Смещение пальца/курсора чуть выше фигуры, как в оригинале
                                self.drag_offset_x = sw // 2
                                self.drag_offset_y = sh + 20
                                break

                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if self.dragged_shape:
                        # Расчет координат на сетке
                        shape_px = mouse_x - self.drag_offset_x
                        shape_py = mouse_y - self.drag_offset_y

                        grid_c = round((shape_px - GRID_OFFSET_X) / CELL_SIZE)
                        grid_r = round((shape_py - GRID_OFFSET_Y) / CELL_SIZE)

                        if self.can_fit_shape(self.dragged_shape, grid_r, grid_c):
                            self.place_shape(self.dragged_shape, grid_r, grid_c)
                            self.available_shapes[self.dragged_index] = None
                            self.can_swap_pocket = True

                            # Если все 3 использованы, спавним новую тройку
                            if all(s is None for s in self.available_shapes):
                                self.refill_shapes()

                            # Проверка окончания игры
                            if not self.has_any_valid_moves():
                                self.game_over = True
                                play_sound(280, 120, 0.3, 0.4)
                        else:
                            play_sound(180, 150, 0.05, 0.15)

                        self.dragged_shape.is_dragging = False
                        self.dragged_shape = None
                        self.dragged_index = -1

            # --- Обновление ---
            for p in self.particles[:]:
                p.update()
                if p.alpha <= 0:
                    self.particles.remove(p)

            for ft in self.floating_texts[:]:
                ft.update()
                if ft.life <= 0:
                    self.floating_texts.remove(ft)

            # --- Отрисовка ---
            render_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
            render_surf.fill(COLOR_BG)

            # Овердрайв пульс на фоне
            if self.combo >= 3:
                pulse = int((math.sin(pygame.time.get_ticks() * 0.008) + 1) * 15)
                overdrive_overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
                overdrive_overlay.fill((40 + pulse, 15, 60 + pulse))
                render_surf.blit(overdrive_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

            # Верхняя панель: Счет и Рекорд
            score_txt = self.font_big.render(str(self.score), True, COLOR_TEXT)
            render_surf.blit(score_txt, (35, 30))

            high_lbl = self.font_small.render(f"👑 BEST: {self.high_score}", True, COLOR_GOLD)
            render_surf.blit(high_lbl, (37, 75))

            if self.combo >= 3:
                fever_lbl = self.font_mid.render("⚡ NEON FEVER (x3)", True, COLOR_ACCENT)
                render_surf.blit(fever_lbl, (35, 98))

            # Карман (Hold Pocket Slot)
            pocket_rect = pygame.Rect(WINDOW_WIDTH - 95, 30, 70, 70)
            pygame.draw.rect(render_surf, COLOR_GRID_BG, pocket_rect, border_radius=10)
            pygame.draw.rect(render_surf, COLOR_ACCENT if self.can_swap_pocket else COLOR_GRID_LINE, pocket_rect, 2,
                             border_radius=10)
            pocket_title = self.font_small.render("HOLD [SPC]", True, COLOR_TEXT_DIM)
            render_surf.blit(pocket_title, (WINDOW_WIDTH - 98, 12))

            if self.pocket_shape:
                pw = self.pocket_shape.get_width(CELL_SIZE * 0.45)
                ph = self.pocket_shape.get_height(CELL_SIZE * 0.45)
                px = pocket_rect.centerx - pw // 2
                py = pocket_rect.centery - ph // 2
                self.pocket_shape.draw(render_surf, px, py, int(CELL_SIZE * 0.45))

            # Сетка 8x8
            grid_bg_rect = pygame.Rect(GRID_OFFSET_X - 6, GRID_OFFSET_Y - 6, (GRID_SIZE * CELL_SIZE) + 12,
                                       (GRID_SIZE * CELL_SIZE) + 12)
            pygame.draw.rect(render_surf, COLOR_GRID_BG, grid_bg_rect, border_radius=14)

            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    rx = GRID_OFFSET_X + c * CELL_SIZE
                    ry = GRID_OFFSET_Y + r * CELL_SIZE
                    inner_cell = pygame.Rect(rx + 2, ry + 2, CELL_SIZE - 4, CELL_SIZE - 4)
                    pygame.draw.rect(render_surf, (22, 22, 36), inner_cell, border_radius=6)

                    # Заполненные блоки
                    if self.grid[r][c] == 1:
                        color = self.grid_colors[r][c] or COLOR_ACCENT
                        pygame.draw.rect(render_surf, color, inner_cell, border_radius=6)
                        pygame.draw.line(render_surf, (255, 255, 255, 100), (rx + 4, ry + 4),
                                         (rx + CELL_SIZE - 6, ry + 4), 2)

            # Проекция (Shadow Snapping) при перетаскивании
            if self.dragged_shape:
                shape_px = mouse_x - self.drag_offset_x
                shape_py = mouse_y - self.drag_offset_y
                grid_c = round((shape_px - GRID_OFFSET_X) / CELL_SIZE)
                grid_r = round((shape_py - GRID_OFFSET_Y) / CELL_SIZE)

                if self.can_fit_shape(self.dragged_shape, grid_r, grid_c):
                    for r in range(self.dragged_shape.rows):
                        for c in range(self.dragged_shape.cols):
                            if self.dragged_shape.matrix[r][c]:
                                hx = GRID_OFFSET_X + (grid_c + c) * CELL_SIZE + 2
                                hy = GRID_OFFSET_Y + (grid_r + r) * CELL_SIZE + 2
                                ghost_surf = pygame.Surface((CELL_SIZE - 4, CELL_SIZE - 4), pygame.SRCALPHA)
                                ghost_surf.fill((*self.dragged_shape.color, 110))
                                render_surf.blit(ghost_surf, (hx, hy))

            # Частицы
            for p in self.particles:
                p.draw(render_surf)

            # Отрисовка фигур в слотах внизу
            for shape in self.available_shapes:
                if shape and not shape.is_dragging:
                    shape.draw(render_surf, shape.base_x, shape.base_y, int(CELL_SIZE * 0.65))

            # Перетаскиваемая фигура в реальном масштабе
            if self.dragged_shape:
                self.dragged_shape.draw(
                    render_surf,
                    mouse_x - self.drag_offset_x,
                    mouse_y - self.drag_offset_y,
                    CELL_SIZE,
                    alpha=240
                )

            # Всплывающий текст
            for ft in self.floating_texts:
                ft.draw(render_surf)

            # Окно Game Over
            if self.game_over:
                overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
                overlay.fill((10, 10, 18, 220))
                render_surf.blit(overlay, (0, 0))

                go_txt = self.font_big.render("GAME OVER", True, (255, 75, 75))
                render_surf.blit(go_txt, ((WINDOW_WIDTH - go_txt.get_width()) // 2, 280))

                sc_txt = self.font_mid.render(f"Final Score: {self.score}", True, COLOR_TEXT)
                render_surf.blit(sc_txt, ((WINDOW_WIDTH - sc_txt.get_width()) // 2, 335))

                restart_txt = self.font_small.render("Нажмите R или Кликните для рестарта", True, COLOR_TEXT_DIM)
                render_surf.blit(restart_txt, ((WINDOW_WIDTH - restart_txt.get_width()) // 2, 385))

            # Вывод на окно со сдвигом от тряски
            self.screen.fill(COLOR_BG)
            self.screen.blit(render_surf, (shake_ox, shake_oy))
            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    app = BlockBlastApp()
    app.run()