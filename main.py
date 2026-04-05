#!/usr/bin/env python3
"""
  Tiny Farm  ·  a minimalist farming RPG
  ───────────────────────────────────────
  Install:  pip install pygame

  Controls:
    Arrow keys / WASD   move
    1 · 2 · 3 · 4       select tool  (Hoe · Watering Can · Seeds · Harvest)
    Space               use tool on the tile you're facing
    Tab                 cycle which seed to plant
    Z                   sleep  (stand inside your house near the bed)
    E                   open shop  (walk through the shop door)
    Esc / Q             quit
"""

import pygame
import sys
from dataclasses import dataclass, field

# ─── init ────────────────────────────────────────────────────────────────────
pygame.init()
pygame.display.set_caption("Tiny Farm")

TILE_PX    = 48
COLS, ROWS = 22, 16
SW, SH     = COLS * TILE_PX, ROWS * TILE_PX   # 1056 × 768
FPS        = 60
MOVE_MS    = 140   # ms between tile steps

# ─── tile IDs ────────────────────────────────────────────────────────────────
GRASS = 0; DIRT = 1; WET = 2; WATER = 3
WALL  = 4; PATH = 5; BED  = 6; SHOP  = 7; FLOOR = 8

PASSABLE = {GRASS, DIRT, WET, PATH, BED, FLOOR, SHOP}

# ─── colours ─────────────────────────────────────────────────────────────────
TILE_COL = {
    GRASS: (106, 148,  70),
    DIRT:  (155, 103,  60),
    WET:   ( 90,  55,  25),
    WATER: ( 64, 164, 223),
    WALL:  ( 90,  58,  25),
    PATH:  (193, 168, 107),
    BED:   (180, 100, 120),
    SHOP:  (100, 155,  85),
    FLOOR: (200, 170, 120),
}

CWHITE  = (245, 240, 225)
CBLACK  = ( 15,  15,  15)
CGOLD   = (230, 190,  40)
CGREEN  = ( 60, 180,  60)
CUI_BG  = ( 30,  20,  10)
CUI_BR  = (200, 160,  80)
CSKIN   = (220, 170, 110)
CHAIR   = (100,  60,  20)
CSHIRT  = ( 80, 120, 180)
CPANTS  = ( 60,  80, 140)
CROP_STEM = (80, 160, 50)

# ─── crop data  (days_to_mature, sell_price, seed_cost, body_colour) ─────────
CROP_INFO = {
    "turnip": (3,  8,  0, (200, 200,  80)),
    "carrot": (4, 15, 10, (230, 120,  40)),
    "melon":  (6, 35, 20, (100, 180,  80)),
}
SEED_NAMES = ["turnip", "carrot", "melon"]

TOOL_NAMES = ["Hoe", "Watering Can", "Seeds", "Harvest"]
TOOL_COLS  = [(140, 90, 30), (40, 130, 210), (80, 170, 50), (210, 170, 40)]


# ─── data classes ────────────────────────────────────────────────────────────
@dataclass
class Crop:
    kind:        str
    planted_day: int
    watered:     bool = False

    def stage(self, day: int) -> int:
        """Return growth stage: 0=seed  1=sprout  2=growing  3=ready"""
        age  = day - self.planted_day
        need = CROP_INFO[self.kind][0]
        if age <= 0:    return 0
        if age >= need: return 3
        frac = age / need
        return 1 if frac < 0.4 else 2

    def ready(self, day: int) -> bool:
        return day - self.planted_day >= CROP_INFO[self.kind][0]


@dataclass
class Player:
    x:        int  = 3
    y:        int  = 6    # start on path between buildings
    dx:       int  = 0
    dy:       int  = 1    # facing south
    tool:     int  = 0
    gold:     int  = 50
    seeds:    dict = field(default_factory=lambda: {"turnip": 5})
    bag:      dict = field(default_factory=dict)
    seed_idx: int  = 0
    move_at:  int  = 0    # ticks when last moved


# ─── map builder ─────────────────────────────────────────────────────────────
def build_map() -> list[list[int]]:
    g = [[GRASS] * COLS for _ in range(ROWS)]

    def fill(r0, c0, r1, c1, t):
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                g[r][c] = t

    def box(r0, c0, r1, c1, wall_t=WALL, inner_t=FLOOR):
        fill(r0, c0, r1, c1, inner_t)
        for c in range(c0, c1 + 1):
            g[r0][c] = wall_t
            g[r1][c] = wall_t
        for r in range(r0, r1 + 1):
            g[r][c0] = wall_t
            g[r][c1] = wall_t

    # World border
    box(0, 0, ROWS - 1, COLS - 1, WALL, GRASS)

    # House  (rows 1–4, cols 1–5)
    box(1, 1, 4, 5, WALL, FLOOR)
    g[2][3] = BED        # bed inside
    g[4][2] = FLOOR      # south door opening (left)
    g[4][3] = FLOOR      # south door opening (right)

    # Pond  (rows 1–3, cols 7–10)
    fill(1, 7, 3, 10, WATER)

    # Shop  (rows 7–10, cols 1–5)
    box(7, 1, 10, 5, WALL, SHOP)
    g[10][2] = FLOOR     # south door opening (left)
    g[10][3] = FLOOR     # south door opening (right)

    # Paths
    fill(5,  1,  5, 10, PATH)    # east–west between house & farm
    fill(11, 1, 11, 10, PATH)    # east–west below shop
    fill(1,  6,  6,  6, PATH)    # north–south left of pond
    fill(6,  1,  6,  6, PATH)    # row connecting house side-path
    fill(1, 11, 13, 11, PATH)    # north–south path into farm
    fill(7,  6,  7, 11, PATH)    # mid east–west shortcut

    return g


# ─── game ────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SW, SH))
        self.clock  = pygame.time.Clock()
        self.font   = pygame.font.SysFont("monospace", 15)
        self.font_b = pygame.font.SysFont("monospace", 20, bold=True)

        self.grid   = build_map()
        self.crops: dict[tuple[int, int], Crop] = {}
        self.player = Player()
        self.day    = 1

        self.shop_open = False
        self.shop_sel  = 0
        self.msg       = ""
        self.msg_ticks = 0

        # Shop buy menu: (label, gold_cost, crop_kind, qty)
        self.buy_items = [
            ("Carrot Seeds  ×5",  10, "carrot",  5),
            ("Melon Seeds   ×5",  20, "melon",   5),
            ("Carrot Seeds  ×10", 18, "carrot", 10),
            ("Melon Seeds   ×10", 35, "melon",  10),
        ]

    # ── helpers ──────────────────────────────────────────────────────────────
    def tile(self, x, y) -> int:
        if 0 <= x < COLS and 0 <= y < ROWS:
            return self.grid[y][x]
        return WALL

    def facing(self) -> tuple[int, int]:
        p = self.player
        return p.x + p.dx, p.y + p.dy

    def msg_show(self, txt: str, ticks: int = 220):
        self.msg       = txt
        self.msg_ticks = ticks

    def near(self, tile_type: int) -> bool:
        """True if player or any 4-neighbour tile equals tile_type."""
        p = self.player
        for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]:
            if self.tile(p.x + dx, p.y + dy) == tile_type:
                return True
        return False

    # ── day / sleep ──────────────────────────────────────────────────────────
    def sleep(self):
        if not self.near(BED):
            self.msg_show("Sleep in your bed — go inside your house.")
            return
        self.day += 1
        for crop in self.crops.values():
            crop.watered = False
        self.msg_show(f"  Good morning!  Day {self.day} begins.  ")

    # ── tool use ─────────────────────────────────────────────────────────────
    def use_tool(self):
        p = self.player
        fx, fy = self.facing()
        t = self.tile(fx, fy)

        if p.tool == 0:       # Hoe
            if t == GRASS:
                self.grid[fy][fx] = DIRT
                self.msg_show("Tilled the soil.")
            else:
                self.msg_show("Can only till grass tiles.")

        elif p.tool == 1:     # Watering Can
            if t in (DIRT, WET) and (fx, fy) in self.crops:
                self.grid[fy][fx] = WET
                self.crops[(fx, fy)].watered = True
                self.msg_show("Watered!")
            elif t in (DIRT, WET):
                self.msg_show("Nothing is planted here.")
            else:
                self.msg_show("Water only tilled soil.")

        elif p.tool == 2:     # Seeds
            kind = SEED_NAMES[p.seed_idx]
            if t in (DIRT, WET):
                if (fx, fy) not in self.crops:
                    if p.seeds.get(kind, 0) > 0:
                        self.crops[(fx, fy)] = Crop(kind, self.day)
                        p.seeds[kind] -= 1
                        self.msg_show(f"Planted {kind}.")
                    else:
                        self.msg_show(f"No {kind} seeds!  Buy some at the shop.")
                else:
                    self.msg_show("Something is already planted here.")
            else:
                self.msg_show("Need tilled soil first  (use Hoe).")

        elif p.tool == 3:     # Harvest
            if (fx, fy) in self.crops:
                crop = self.crops[(fx, fy)]
                if crop.ready(self.day):
                    p.bag[crop.kind] = p.bag.get(crop.kind, 0) + 1
                    del self.crops[(fx, fy)]
                    self.grid[fy][fx] = DIRT
                    sell = CROP_INFO[crop.kind][1]
                    self.msg_show(f"Harvested {crop.kind}!  Sells for {sell}g.")
                else:
                    rem = CROP_INFO[crop.kind][0] - (self.day - crop.planted_day)
                    self.msg_show(f"Not ready — {rem} more day(s).")
            else:
                self.msg_show("Nothing to harvest here.")

    # ── shop ─────────────────────────────────────────────────────────────────
    def open_shop(self):
        if not self.near(SHOP):
            self.msg_show("Walk to the shop first.")
            return
        self.shop_open = True
        self.shop_sel  = 0

    def shop_confirm(self):
        p  = self.player
        bi = self.buy_items
        n  = len(bi)

        if self.shop_sel < n:
            _lbl, cost, kind, qty = bi[self.shop_sel]
            if p.gold >= cost:
                p.gold -= cost
                p.seeds[kind] = p.seeds.get(kind, 0) + qty
                self.msg_show(f"Bought {qty}× {kind} seeds!")
            else:
                self.msg_show("Not enough gold!")
        else:
            # Sell all crops
            total = sum(CROP_INFO[k][1] * v for k, v in p.bag.items())
            if total:
                p.gold += total
                p.bag.clear()
                self.msg_show(f"Sold everything for {total}g!")
            else:
                self.msg_show("Your bag is empty.")

    # ── events ───────────────────────────────────────────────────────────────
    def handle_events(self):
        p   = self.player
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN:
                k = event.key

                if self.shop_open:
                    n_opts = len(self.buy_items) + 1
                    if k == pygame.K_ESCAPE:
                        self.shop_open = False
                    elif k in (pygame.K_UP, pygame.K_w):
                        self.shop_sel = (self.shop_sel - 1) % n_opts
                    elif k in (pygame.K_DOWN, pygame.K_s):
                        self.shop_sel = (self.shop_sel + 1) % n_opts
                    elif k in (pygame.K_SPACE, pygame.K_RETURN):
                        self.shop_confirm()
                    continue   # shop swallows all keys

                if k in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit(); sys.exit()
                if k == pygame.K_1: p.tool = 0
                if k == pygame.K_2: p.tool = 1
                if k == pygame.K_3: p.tool = 2
                if k == pygame.K_4: p.tool = 3
                if k == pygame.K_TAB:
                    p.seed_idx = (p.seed_idx + 1) % len(SEED_NAMES)
                    self.msg_show(f"Seed selected: {SEED_NAMES[p.seed_idx]}")
                if k in (pygame.K_SPACE, pygame.K_RETURN):
                    self.use_tool()
                if k == pygame.K_z:
                    self.sleep()
                if k == pygame.K_e:
                    self.open_shop()

        # Smooth held-key movement (step every MOVE_MS ms)
        if not self.shop_open and now - p.move_at >= MOVE_MS:
            keys = pygame.key.get_pressed()
            dx = dy = 0
            if   keys[pygame.K_UP]    or keys[pygame.K_w]: dy = -1
            elif keys[pygame.K_DOWN]  or keys[pygame.K_s]: dy =  1
            if   keys[pygame.K_LEFT]  or keys[pygame.K_a]: dx = -1
            elif keys[pygame.K_RIGHT] or keys[pygame.K_d]: dx =  1
            if dx or dy:
                p.dx, p.dy = dx, dy
                nx, ny = p.x + dx, p.y + dy
                if self.tile(nx, ny) in PASSABLE:
                    p.x, p.y = nx, ny
                p.move_at = now

    # ── drawing ──────────────────────────────────────────────────────────────
    def draw_tiles(self):
        s = self.screen
        for r in range(ROWS):
            for c in range(COLS):
                t = self.grid[r][c]
                # Checkerboard tint on grass for depth
                if t == GRASS:
                    col = (106, 148, 70) if (r + c) % 2 == 0 else (96, 138, 62)
                elif t == WATER:
                    col = (64, 164, 223) if (r + c) % 2 == 0 else (54, 148, 210)
                else:
                    col = TILE_COL.get(t, (80, 80, 80))
                rect = pygame.Rect(c * TILE_PX, r * TILE_PX, TILE_PX, TILE_PX)
                pygame.draw.rect(s, col, rect)
                pygame.draw.rect(s, CBLACK, rect, 1)

        # House roof band + label
        pygame.draw.rect(s, (160, 50, 50),
                         pygame.Rect(1 * TILE_PX, 0, 5 * TILE_PX, TILE_PX))
        ht = self.font_b.render("Home", True, CWHITE)
        s.blit(ht, (1 * TILE_PX + 16, 4))

        # Shop roof band + label
        pygame.draw.rect(s, (55, 110, 60),
                         pygame.Rect(1 * TILE_PX, 6 * TILE_PX, 5 * TILE_PX, TILE_PX))
        st = self.font_b.render("Shop", True, CWHITE)
        s.blit(st, (1 * TILE_PX + 16, 6 * TILE_PX + 6))

        # Farm label
        farm_lbl = self.font.render("— farm —", True, (130, 160, 90))
        s.blit(farm_lbl, (13 * TILE_PX, 14 * TILE_PX + 12))

    def draw_crops(self):
        s = self.screen
        for (cx, cy), crop in self.crops.items():
            stg   = crop.stage(self.day)
            color = CROP_INFO[crop.kind][3]
            px    = cx * TILE_PX + TILE_PX // 2
            py    = cy * TILE_PX + TILE_PX // 2

            if stg == 0:   # seed — small brown dot
                pygame.draw.circle(s, (140, 110, 50), (px, py + 10), 4)
            elif stg == 1: # sprout
                pygame.draw.line(s, CROP_STEM, (px, py + 14), (px, py + 4), 2)
                pygame.draw.circle(s, CROP_STEM, (px, py + 2), 5)
            elif stg == 2: # growing
                pygame.draw.line(s, CROP_STEM, (px, py + 14), (px, py + 4), 3)
                pygame.draw.circle(s, color, (px, py + 2), 9)
                pygame.draw.circle(s, CROP_STEM, (px - 9, py + 8), 5)
            else:          # ready — bigger + highlight
                pygame.draw.line(s, CROP_STEM, (px, py + 14), (px, py + 2), 3)
                pygame.draw.circle(s, color, (px, py), 13)
                hi = tuple(min(255, c + 60) for c in color)
                pygame.draw.circle(s, hi, (px - 4, py - 4), 5)

            # Watered indicator — small blue dot
            if crop.watered:
                pygame.draw.circle(s, (80, 160, 240), (cx * TILE_PX + 6, cy * TILE_PX + 6), 3)

    def draw_player(self):
        s  = self.screen
        p  = self.player
        px = p.x * TILE_PX + TILE_PX // 2
        py = p.y * TILE_PX + TILE_PX // 2

        # Legs
        pygame.draw.rect(s, CPANTS, (px - 7, py + 8,  6, 10))
        pygame.draw.rect(s, CPANTS, (px + 1, py + 8,  6, 10))
        # Body / shirt
        pygame.draw.rect(s, CSHIRT, (px - 8, py - 4, 16, 14))
        # Head
        pygame.draw.circle(s, CSKIN, (px, py - 10), 9)
        # Hair
        pygame.draw.rect(s, CHAIR, (px - 9, py - 20, 18, 9))

        # Eyes face direction
        if   p.dy ==  1: eyes = [(px - 3, py - 9), (px + 3, py - 9)]
        elif p.dy == -1: eyes = [(px - 3, py - 11), (px + 3, py - 11)]
        else:            eyes = [(px + p.dx * 5, py - 10)]
        for ex, ey in eyes:
            pygame.draw.circle(s, CBLACK, (ex, ey), 2)

    def draw_hud(self):
        s = self.screen
        p = self.player

        # Top bar
        pygame.draw.rect(s, CUI_BG, (0, 0, SW, 34))
        pygame.draw.rect(s, CUI_BR, (0, 33, SW, 2))

        # Day & gold
        ds = self.font_b.render(f" Day {self.day} ", True, CGOLD)
        gs = self.font_b.render(f" {p.gold}g ", True, CGOLD)
        s.blit(ds, (8, 6))
        s.blit(gs, (8 + ds.get_width() + 12, 6))

        # Tool bar
        for i, (name, col) in enumerate(zip(TOOL_NAMES, TOOL_COLS)):
            tx  = 260 + i * 148
            sel = (i == p.tool)
            if sel:
                pygame.draw.rect(s, col,    (tx - 2, 2, 142, 30))
                pygame.draw.rect(s, CWHITE, (tx - 2, 2, 142, 30), 2)
            tc = CWHITE if sel else (150, 140, 120)
            s.blit(self.font.render(f"{i + 1}: {name}", True, tc), (tx + 4, 9))

        # Bag contents (top-right)
        if p.bag:
            bag = "Bag: " + "  ".join(f"{k}×{v}" for k, v in p.bag.items())
            bs  = self.font.render(bag, True, CWHITE)
            s.blit(bs, (SW - bs.get_width() - 8, 8))

        # Bottom bar
        pygame.draw.rect(s, CUI_BG, (0, SH - 28, SW, 28))
        pygame.draw.rect(s, CUI_BR, (0, SH - 29, SW, 1))

        if p.tool == 2:
            kind   = SEED_NAMES[p.seed_idx]
            count  = p.seeds.get(kind, 0)
            seed_s = self.font.render(
                f"[Tab] Planting: {kind} ×{count}    ", True, CGREEN)
            s.blit(seed_s, (8, SH - 22))

        hint = self.font.render(
            "Space:use tool   Z:sleep   E:open shop   Esc:quit", True, (130, 120, 100))
        s.blit(hint, (SW // 2 - hint.get_width() // 2, SH - 22))

    def draw_shop(self):
        s  = self.screen
        p  = self.player
        PW = 440
        PH = 310

        px = SW // 2 - PW // 2
        py = SH // 2 - PH // 2

        panel = pygame.Surface((PW, PH))
        panel.fill(CUI_BG)
        s.blit(panel, (px, py))
        pygame.draw.rect(s, CUI_BR, (px, py, PW, PH), 3)

        title = self.font_b.render("  ~ Pierre's General Store ~  ", True, CGOLD)
        s.blit(title, (px + PW // 2 - title.get_width() // 2, py + 10))
        pygame.draw.line(s, CUI_BR, (px + 10, py + 38), (px + PW - 10, py + 38), 1)

        # Build option list: buy items + sell-all
        bag_val  = sum(CROP_INFO[k][1] * v for k, v in p.bag.items())
        opts = [f"Buy: {lbl}  ({cost}g)" for lbl, cost, _, _ in self.buy_items]
        opts.append(f"Sell All Crops  (bag worth {bag_val}g)")
        n = len(opts)

        for i, opt in enumerate(opts):
            oy  = py + 52 + i * 32
            sel = (i == self.shop_sel)
            if sel:
                pygame.draw.rect(s, (60, 45, 20), (px + 8, oy - 2, PW - 16, 28))
                s.blit(self.font.render(">", True, CGOLD), (px + 4, oy))
            col = CWHITE if sel else (170, 160, 140)
            if i == n - 1 and bag_val > 0:
                col = CGREEN
            s.blit(self.font.render(opt, True, col), (px + 18, oy))

        # Footer info
        sep_y = py + PH - 58
        pygame.draw.line(s, (60, 45, 20), (px + 10, sep_y), (px + PW - 10, sep_y), 1)

        gold_s = self.font.render(f"Your gold: {p.gold}g", True, CGOLD)
        seed_s = self.font.render(
            "Seeds: " + (", ".join(f"{k}:{v}" for k, v in p.seeds.items()) or "none"),
            True, CGREEN)
        hint_s = self.font.render(
            "↑↓ navigate    Space / Enter to buy or sell    Esc close",
            True, (120, 110, 90))

        s.blit(gold_s, (px + 12, py + PH - 52))
        s.blit(seed_s, (px + 12, py + PH - 34))
        s.blit(hint_s, (px + PW // 2 - hint_s.get_width() // 2, py + PH - 14))

    def draw_msg(self):
        if not self.msg_ticks:
            return
        self.msg_ticks -= 1
        surf = self.font_b.render(self.msg, True, CWHITE)
        bw   = surf.get_width() + 24
        bh   = 32
        bx   = SW // 2 - bw // 2
        by   = SH - 75
        bg   = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 190))
        self.screen.blit(bg, (bx, by))
        self.screen.blit(surf, (bx + 12, by + 6))

    # ── main loop ────────────────────────────────────────────────────────────
    def run(self):
        while True:
            self.handle_events()

            self.screen.fill((20, 20, 20))
            self.draw_tiles()
            self.draw_crops()
            self.draw_player()
            self.draw_hud()
            if self.shop_open:
                self.draw_shop()
            self.draw_msg()

            pygame.display.flip()
            self.clock.tick(FPS)


if __name__ == "__main__":
    Game().run()
