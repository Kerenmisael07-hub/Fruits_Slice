import cv2
import mediapipe as mp
import pygame
import random
import os
import math
import numpy as np
import time
import json

# Initialize pygame and create screen before creating fonts
pygame.init()
width, height = 800, 600
screen = pygame.display.set_mode((width, height))
pygame.display.set_caption("🍉 Fruit Slice by Keren")

# Initialize MediaPipe hands
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands(max_num_hands=1)

font = pygame.font.SysFont("Comic Sans MS", 32)
small_font = pygame.font.SysFont("Comic Sans MS", 20)
tiny_font = pygame.font.SysFont("Comic Sans MS", 16)
combo_font = pygame.font.SysFont("Comic Sans MS", 56, bold=True)
clock = pygame.time.Clock()

# --- UI / Game state ---
game_state = "menu"  # menu | playing | settings
music_on = True
sfx_on = True

# menu button geometry (computed relative to screen)
btn_w, btn_h = 240, 64
btn_x = (width - btn_w) // 2
btn_y_start = 160
btn_gap = 24

# quit-by-5-fingers
quit_hold_frames = 0
quit_hold_required = 15  # frames to confirm quit (~0.5s at 30fps)

# helper to count extended fingers (simple tip vs pip test)
def count_extended_fingers(handLms, img_h):
    # landmarks: tip indices [4,8,12,16,20], compare tip.y < pip.y (tip above pip)
    tips = [4, 8, 12, 16, 20]
    count = 0
    for tip in tips:
        tip_y = handLms.landmark[tip].y * img_h
        pip_y = handLms.landmark[tip - 2].y * img_h
        if tip_y < pip_y:
            count += 1
    return count


# --- Sound / Lightning settings ---
try:
    pygame.mixer.init()
except Exception:
    # ignore if audio cannot be initialized in headless env
    pass

# --- Background Music ---
bgm_path = None
for p in ("sound.mp3", os.path.join("sound", "sound.mp3")):
    if os.path.exists(p):
        bgm_path = p
        break

if bgm_path:
    try:
        pygame.mixer.music.load(bgm_path)
        pygame.mixer.music.set_volume(0.4)  # sesuaikan volume
        pygame.mixer.music.play(-1)  # loop terus
    except Exception as e:
        print("Gagal memutar BGM:", e)

slash_sound = None
# look for several reasonable filenames in project root and sounds/ folder
for name in ("terbelah.mp3", "terbelah.mp3", "terbelah.mp3", "terbelah.mp3", "terbelah.mp3"):
    for p in (name, os.path.join("sound", name)):
        if os.path.exists(p):
            try:
                slash_sound = pygame.mixer.Sound(p)
                slash_sound.set_volume(0.3)
                break
            except Exception:
                slash_sound = None
                break
    if slash_sound:
        break

# split sound (explicit) - played when fruit actually splits
split_sound = None
for name in ("terbelah.mp3", "split.mp3", "split.wav", os.path.join("sounds", "terbelah.mp3"), os.path.join("sounds", "split.wav")):
    if os.path.exists(name):
        try:
            split_sound = pygame.mixer.Sound(name)
            split_sound.set_volume(0.7)
            break
        except Exception:
            split_sound = None
            break

# throw sound (played when fruit spawns)
throw_sound = None
for basename in ("lemparbuah.mp3", "lemparbuah.wav"):
    # check several candidate locations: current dir, sound/, sounds/
    for p in (basename, os.path.join("sound", basename), os.path.join("sound", basename)):
        if os.path.exists(p):
            try:
                throw_sound = pygame.mixer.Sound(p)
                throw_sound.set_volume(1.0)
                break
            except Exception:
                throw_sound = None
                break
    if throw_sound:
        break

# combo / thunder sound for combo lightning effect
combo_sound = None
for basename in ("petir.mp3", "petir.mp3", "thunder.mp3", "thunder.wav"):
    for p in (basename, os.path.join("sound", basename), os.path.join("sounds", basename)):
        if os.path.exists(p):
            try:
                combo_sound = pygame.mixer.Sound(p)
                combo_sound.set_volume(0.9)
                break
            except Exception:
                combo_sound = None
                break
    if combo_sound:
        break

lightning_threshold = 40  # px/frame
lightning_duration = 6  # frames to show lightning after a fast move
lightning_timer = 0
_lightning_was_fast = False

# --- Muat gambar buah ---
def load_image(name_or_path):
    # Accept either a basename inside the fruits/ folder or a full path
    if os.path.isabs(name_or_path) or os.path.sep in name_or_path:
        path = name_or_path
    else:
        path = os.path.join("fruits", name_or_path)
    img = pygame.image.load(path).convert_alpha()
    return pygame.transform.scale(img, (80, 80))

# Dynamically load all PNG images from the fruits/ directory
fruit_images = []
fruits_dir = os.path.join(os.path.dirname(__file__), "fruits") if '__file__' in globals() else "fruits"
if not os.path.isdir(fruits_dir):
    fruits_dir = "fruits"

try:
    for fname in sorted(os.listdir(fruits_dir)):
        if fname.lower().endswith('.png'):
            try:
                img = load_image(os.path.join(fruits_dir, fname))
                name = os.path.splitext(fname)[0].lower()
                fruit_images.append((img, name))
            except Exception as e:
                print(f"Failed to load fruit image '{fname}':", e)
except Exception as e:
    print("Error listing fruits directory:", e)

# --- Load anomaly (obstacle) assets ---
boom_img = None
boom_sound = None
anomali_dir = os.path.join(os.path.dirname(__file__), "anomali") if '__file__' in globals() else "anomali"
if not os.path.isdir(anomali_dir):
    anomali_dir = "anomali"

try:
    boom_path = os.path.join(anomali_dir, "boom.png")
    if os.path.exists(boom_path):
        try:
            boom_img = load_image(boom_path)
        except Exception as e:
            try:
                boom_img = pygame.image.load(boom_path).convert_alpha()
                boom_img = pygame.transform.scale(boom_img, (64, 64))
            except Exception:
                boom_img = None
    # optional boom sound (legacy) and dedicated timer/explosion sounds from sound/ folder
    boom_sound = None
    for name in ("boom.wav", "boom.mp3", "boom.ogg"):
        p = os.path.join(anomali_dir, name)
        if os.path.exists(p):
            try:
                boom_sound = pygame.mixer.Sound(p)
                boom_sound.set_volume(0.8)
                break
            except Exception:
                boom_sound = None
                break

    # dedicated timer (played when boom is thrown) and explosion (played when sliced)
    boom_timer_sound = None
    boom_explosion_sound = None
    try:
        # look in sound/ and sounds/ for the specified filenames
        for fname in ("timerboom.mp3", "timerboom.wav", "timerboom.ogg"):
            p = os.path.join("sound", fname)
            if os.path.exists(p):
                try:
                    boom_timer_sound = pygame.mixer.Sound(p)
                    boom_timer_sound.set_volume(0.8)
                    break
                except Exception:
                    boom_timer_sound = None
                    break

        for fname in ("ledakanboom.mp3", "ledakanboom.wav", "ledakanboom.ogg"):
            p = os.path.join("sound", fname)
            if os.path.exists(p):
                try:
                    boom_explosion_sound = pygame.mixer.Sound(p)
                    boom_explosion_sound.set_volume(0.9)
                    break
                except Exception:
                    boom_explosion_sound = None
                    break
    except Exception:
        boom_timer_sound = boom_timer_sound or None
        boom_explosion_sound = boom_explosion_sound or None
except Exception:
    boom_img = None
    boom_sound = None

# --- Load coin UI image (shop-coin) ---
shop_coin_dir = os.path.join(os.path.dirname(__file__), "shop-coin") if '__file__' in globals() else "shop-coin"
if not os.path.isdir(shop_coin_dir):
    shop_coin_dir = "shop-coin"
try:
    coin_path = os.path.join(shop_coin_dir, "koin.png")
    if os.path.exists(coin_path):
        try:
            coin_img = load_image(coin_path)
        except Exception:
            try:
                ci = pygame.image.load(coin_path).convert_alpha()
                coin_img = pygame.transform.scale(ci, (48, 48))
            except Exception:
                coin_img = None
    else:
        coin_img = None
except Exception:
    coin_img = None

# --- Persisted coin storage ---
coin_data_path = os.path.join(os.path.dirname(__file__), "coin_data.json") if '__file__' in globals() else "coin_data.json"

def load_coin_count():
    global coin_count
    try:
        if os.path.exists(coin_data_path):
            with open(coin_data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                coin_count = int(data.get("coin_count", 0))
                # load purchased items and selected trail if present
                purchased = data.get("purchased", [])
                # populate global purchased_items
                try:
                    purchased_items.clear()
                    for it in purchased:
                        purchased_items.add(it)
                except Exception:
                    pass
                sel = data.get("selected_trail", None)
                if sel:
                    try:
                        # assign to global
                        globals()["selected_trail"] = sel
                    except Exception:
                        pass
        else:
            coin_count = 0
    except Exception:
        coin_count = 0

def save_coin_count():
    try:
        tosave = {"coin_count": int(coin_count), "purchased": list(purchased_items), "selected_trail": globals().get("selected_trail", "default")}
        with open(coin_data_path, "w", encoding="utf-8") as f:
            json.dump(tosave, f)
    except Exception:
        pass

# initialise persisted coins
try:
    load_coin_count()
except Exception:
    coin_count = 0

# --- Variabel Game ---
fruits = []
halves = []  # potongan buah setelah terbelah
splashes = []  # juice splash particles
particles = []  # small spark / fruit particles for explosion
score = 0
# Coins (shop-coin)
coins = []  # coin entities thrown rarely like fruits
coin_count = 0
coin_img = None
# shop / purchase state
purchased_items = set()
selected_trail = "default"  # options: default, neon, rainbow

# transient shop message (text, age, life)
shop_msg = None
# Combo system
combo_count = 0
last_slice_time = 0.0
multiplier = 1
combo_popups = []  # active combo popup animations
# camera shake and combo lightning
camera_shake_timer = 0
camera_shake_intensity = 0
combo_lightning_timer = 0
last_forced_coin_time = time.time()  # coins timer for forced spawn

# Obstacles (anomali)
obstacles = []  # dicts with x,y,vx,vy,img,type
explosion_flash_timer = 0
shockwaves = []
screen_splatters = []  # full-screen splatter overlays (list of dicts)

def spawn_fruit(count=1):
    """Spawn `count` fruits in a small cluster (default 1).

    When spawning multiple fruits, spread them slightly horizontally so they
    don't overlap exactly. Each fruit will get a randomized vx/vy as before.
    """
    base_x = random.randint(100, width - 100)
    # spawn a bit higher so fruits start off-screen but not too low
    y = height + 40

    for i in range(count):
        # spread each fruit horizontally a bit so they don't stack; tighter spread
        offset = random.randint(-28, 28) + int((i - count // 2) * 12)
        x = max(40, min(width - 120, base_x + offset))
        # slightly faster toss so fruits arc higher but not too fast
        vx = random.choice([-7, -5, -3, 3, 5, 7])
        vy = random.randint(-30, -20)  # a bit stronger upward velocity

        img, ftype = random.choice(fruit_images)
        fruits.append({"x": x, "y": y, "vx": vx, "vy": vy, "img": img, "type": ftype})

        # play throw sound when a fruit is spawned (if available)
        try:
            if throw_sound and sfx_on:
                throw_sound.play()
        except Exception:
            pass


def spawn_obstacle():
    """Spawn a single obstacle (boom) that the player should avoid slicing.

    Uses `boom_img` if available; otherwise spawns a simple placeholder.
    """
    x = random.randint(80, width - 80)
    y = height + 20
    vx = random.randint(-6, 6)
    vy = random.randint(-26, -16)
    img = boom_img
    obstacles.append({"x": x, "y": y, "vx": vx, "vy": vy, "img": img, "type": "boom"})
    # optional throw sound for obstacles (re-use throw_sound if boom sound not present)
    try:
        # play timer sound when obstacle is thrown
        if boom_timer_sound and sfx_on:
            boom_timer_sound.play()
        elif boom_sound and sfx_on:
            boom_sound.play()
        elif throw_sound and sfx_on:
            throw_sound.play()
    except Exception:
        pass


def spawn_coin():
    """Spawn a rare coin that the player can slice to collect.

    Coins behave like fruits but are rarer. When sliced they emit particles
    that fly toward the coin UI and increment `coin_count`.
    """
    # spawn similarly to spawn_fruit so the arc/feel matches
    base_x = random.randint(100, width - 100)
    offset = random.randint(-28, 28)
    x = max(40, min(width - 120, base_x + offset))
    y = height + 40
    vx = random.choice([-7, -5, -3, 3, 5, 7])
    vy = random.randint(-30, -20)
    img = coin_img
    coins.append({"x": x, "y": y, "vx": vx, "vy": vy, "img": img, "type": "coin"})
    try:
        if throw_sound and sfx_on:
            throw_sound.play()
    except Exception:
        pass


def make_half_images(img):
    """Return (left_img, right_img) from a full fruit image (assumed 80x80).

    Each half is 40x80 with transparent background.
    """
    w, h = img.get_width(), img.get_height()
    half_w = w // 2

    left = pygame.Surface((half_w, h), pygame.SRCALPHA)
    right = pygame.Surface((half_w, h), pygame.SRCALPHA)

    # blit the left half (0..half_w)
    left.blit(img, (0, 0), (0, 0, half_w, h))
    # blit the right half (half_w..w)
    right.blit(img, (0, 0), (half_w, 0, half_w, h))

    return left, right


def split_fruit(fruit):
    """Replace a fruit with two animated halves.

    The halves list contains dicts with position, velocity, rotation, alpha and lifetime.
    """
    img = fruit["img"]
    left_img, right_img = make_half_images(img)

    fx = fruit["x"]
    fy = fruit["y"]

    life = 45  # frames until removed (~1.5s at 30fps)

    # left half flies to left-up
    halves.append({
        "x": fx,
        "y": fy,
        "vx": random.uniform(-8.0, -4.0),
        "vy": random.uniform(-12.0, -6.0),
        "img": left_img,
        "angle": random.uniform(-10, 10),
        "avel": random.uniform(-5, -1),
        "alpha": 255,
        "life": life,
        "max_life": life,
    })

    # right half flies to right-up
    halves.append({
        "x": fx + left_img.get_width(),
        "y": fy,
        "vx": random.uniform(4.0, 8.0),
        "vy": random.uniform(-12.0, -6.0),
        "img": right_img,
        "angle": random.uniform(-10, 10),
        "avel": random.uniform(1, 5),
        "alpha": 255,
        "life": life,
        "max_life": life,
    })

cap = cv2.VideoCapture(0)

running = True
spawn_timer = 0
finger_trail = []  # posisi jari sebelumnya (untuk efek garis slice)

while running:
    ret, frame = cap.read()
    if not ret:
        break

    # Non-mirror (kanan tetap kanan)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb)
    frame = cv2.resize(rgb, (width, height))
    frame_surface = pygame.surfarray.make_surface(np.rot90(frame))
    # apply camera shake offset when active
    if camera_shake_timer > 0:
        ox = random.randint(-camera_shake_intensity, camera_shake_intensity)
        oy = random.randint(-camera_shake_intensity, camera_shake_intensity)
        screen.blit(frame_surface, (ox, oy))
        camera_shake_timer -= 1
    else:
        screen.blit(frame_surface, (0, 0))

    finger_x, finger_y = None, None
    finger_count = 0
    if results.multi_hand_landmarks:
        for handLms in results.multi_hand_landmarks:
            h, w, c = frame.shape
            finger = handLms.landmark[8]
            # Balik posisi X biar sesuai non-mirror
            finger_x = width - int(finger.x * width)
            finger_y = int(finger.y * height)

            # Simpan posisi jari
            finger_trail.append((finger_x, finger_y))
            if len(finger_trail) > 5:
                finger_trail.pop(0)

            # Deteksi gerakan cepat untuk efek lightning
            if len(finger_trail) > 1:
                x1, y1 = finger_trail[-2]
                x2, y2 = finger_trail[-1]
                d = math.hypot(x2 - x1, y2 - y1)
                fast = d > lightning_threshold
                if fast and not _lightning_was_fast:
                    # mulai flash singkat dan mainkan suara sekali
                    lightning_timer = lightning_duration
                    # hanya tampilkan efek visual untuk lightning; jangan mainkan suara split di sini
                    # (split sound akan dimainkan hanya saat buah benar-benar terbelah)
                    pass
                elif fast:
                    # perpanjang sedikit bila masih cepat
                    lightning_timer = max(lightning_timer, lightning_duration)
                _lightning_was_fast = fast
            # hitung jumlah jari yang terentang untuk gesture quit
            try:
                finger_count = count_extended_fingers(handLms, height)
            except Exception:
                finger_count = 0

    else:
        finger_trail.clear()

    # update quit-by-5-fingers
    if finger_count == 5:
        quit_hold_frames += 1
    else:
        quit_hold_frames = 0
    if quit_hold_frames >= quit_hold_required:
        running = False

    # (fist-scroll removed)

    # Efek garis slice (trail neon)
    if len(finger_trail) > 1:
        # support multiple trail styles: default, neon (blue), rainbow
        def hsv_to_rgb(h, s, v):
            # h in [0,1], s,v in [0,1]
            i = int(h * 6.0)
            f = (h * 6.0) - i
            p = v * (1.0 - s)
            q = v * (1.0 - f * s)
            t = v * (1.0 - (1.0 - f) * s)
            i = i % 6
            if i == 0:
                r, g, b = v, t, p
            elif i == 1:
                r, g, b = q, v, p
            elif i == 2:
                r, g, b = p, v, t
            elif i == 3:
                r, g, b = p, q, v
            elif i == 4:
                r, g, b = t, p, v
            else:
                r, g, b = v, p, q
            return int(r * 255), int(g * 255), int(b * 255)

        for i in range(len(finger_trail) - 1):
            start = finger_trail[i]
            end = finger_trail[i + 1]
            # compute base thickness
            thickness = max(1, 6 - i)
            if globals().get("selected_trail", "default") == "neon":
                color = (30, 200, 255)
            elif globals().get("selected_trail", "default") == "rainbow":
                # hue varies along the trail
                h = (i / max(1, len(finger_trail) - 1))
                # rotate hue a bit over time for animated rainbow
                h = (h + (time.time() * 0.08)) % 1.0
                color = hsv_to_rgb(h, 0.95, 0.95)
            else:
                color = (0, 255, max(60, 255 - i * 40))
            pygame.draw.line(screen, color, start, end, thickness)

    # Crosshair keren (target)
    if finger_x and finger_y:
        pygame.draw.circle(screen, (255, 255, 255), (finger_x, finger_y), 15, 2)
        pygame.draw.circle(screen, (0, 255, 255), (finger_x, finger_y), 5)
        pygame.draw.line(screen, (0, 255, 255), (finger_x - 20, finger_y), (finger_x + 20, finger_y), 1)
        pygame.draw.line(screen, (0, 255, 255), (finger_x, finger_y - 20), (finger_x, finger_y + 20), 1)

    # Jika di menu atau settings, tampilkan UI dan jangan spawn buah
    if game_state == "playing":
        # Spawn buah tiap 60 frame (slower spawn rate to reduce crowding)
        spawn_timer += 1
        if spawn_timer > 60:
            # Make most spawns single fruits; occasionally spawn a small group (2-3)
            if random.random() < 0.70:
                num = 1
            else:
                num = random.randint(2, 3)
            # small chance to spawn an obstacle (boom) instead of fruits
            # forced coin spawn every 1 minute 25 seconds (85s)
            try:
                if time.time() - last_forced_coin_time >= 85:
                    spawn_coin()
                    last_forced_coin_time = time.time()
            except Exception:
                pass

            # rare coin spawn (very infrequent)
            if coin_img and random.random() < 0.04:
                spawn_coin()
            # small chance to spawn an obstacle (boom)
            elif boom_img and random.random() < 0.12:
                spawn_obstacle()
            else:
                spawn_fruit(count=num)
            spawn_timer = 0
        # In-game Home button (top-left) to return to main menu
        try:
            # move home button a bit lower for easier tapping
            home_rect = pygame.Rect(10, 60, 92, 34)
            pygame.draw.rect(screen, (40, 40, 40), home_rect, border_radius=8)
            home_txt = tiny_font.render("Home", True, (255, 255, 255))
            screen.blit(home_txt, (home_rect.x + (home_rect.w - home_txt.get_width()) // 2, home_rect.y + (home_rect.h - home_txt.get_height()) // 2))

            # detect click or finger tap on Home
            mx, my = pygame.mouse.get_pos()
            mouse_pressed = pygame.mouse.get_pressed()[0]
            if (finger_x and finger_y and home_rect.collidepoint(finger_x, finger_y)) or (home_rect.collidepoint(mx, my) and mouse_pressed):
                # go back to menu and clear gameplay lists
                game_state = "menu"
                finger_trail.clear()
                fruits.clear()
                halves.clear()
                splashes.clear()
                particles.clear()
                obstacles.clear()
                combo_popups.clear()
                spawn_timer = 0
        except Exception:
            pass
    else:
        # Gambar menu / pengaturan
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        if game_state == "menu":
            title = font.render("Fruit Slice 🎮", True, (255, 255, 255))
            screen.blit(title, ((width - title.get_width()) // 2, 60))

            labels = ["Play", "Shop", "Settings", "Quit"]
            mouse_pressed = pygame.mouse.get_pressed()[0]
            mx, my = pygame.mouse.get_pos()
            for i, lbl in enumerate(labels):
                ry = btn_y_start + i * (btn_h + btn_gap)
                rect = pygame.Rect(btn_x, ry, btn_w, btn_h)
                inside = False
                if finger_x and finger_y and rect.collidepoint(finger_x, finger_y):
                    inside = True
                if rect.collidepoint(mx, my) and mouse_pressed:
                    inside = True

                color = (40, 120, 220) if inside else (30, 30, 30)
                pygame.draw.rect(screen, color, rect, border_radius=8)
                txt = font.render(lbl, True, (255, 255, 255))
                screen.blit(txt, (rect.x + (rect.w - txt.get_width()) // 2, rect.y + (rect.h - txt.get_height()) // 2))

                # handle selection (finger point or mouse click)
                if inside:
                    if lbl == "Play":
                        game_state = "playing"
                        finger_trail.clear()
                        fruits.clear()
                        halves.clear()
                        spawn_timer = 0
                    elif lbl == "Shop":
                        game_state = "shop"
                    elif lbl == "Settings":
                        game_state = "settings"
                    elif lbl == "Quit":
                        running = False

        elif game_state == "settings":
            title = font.render("Settings", True, (255, 255, 255))
            screen.blit(title, ((width - title.get_width()) // 2, 60))

            # music toggle
            music_txt = font.render(f"Music: {'On' if music_on else 'Off'}", True, (255, 255, 255))
            music_rect = pygame.Rect(btn_x, btn_y_start, btn_w, btn_h)
            pygame.draw.rect(screen, (40, 40, 40), music_rect, border_radius=8)
            screen.blit(music_txt, (music_rect.x + 12, music_rect.y + 12))

            # sfx toggle
            sfx_txt = font.render(f"SFX: {'On' if sfx_on else 'Off'}", True, (255, 255, 255))
            sfx_rect = pygame.Rect(btn_x, btn_y_start + btn_h + btn_gap, btn_w, btn_h)
            pygame.draw.rect(screen, (40, 40, 40), sfx_rect, border_radius=8)
            screen.blit(sfx_txt, (sfx_rect.x + 12, sfx_rect.y + 12))

            # back button
            back_rect = pygame.Rect(btn_x, btn_y_start + 2 * (btn_h + btn_gap), btn_w, btn_h)
            pygame.draw.rect(screen, (80, 80, 80), back_rect, border_radius=8)
            back_txt = font.render("Back", True, (255, 255, 255))
            screen.blit(back_txt, (back_rect.x + (back_rect.w - back_txt.get_width()) // 2, back_rect.y + 12))

            # handle toggles via finger or mouse
            mx, my = pygame.mouse.get_pos()
            clicked = pygame.mouse.get_pressed()[0]
            if (finger_x and finger_y and music_rect.collidepoint(finger_x, finger_y)) or (music_rect.collidepoint(mx, my) and clicked):
                music_on = not music_on
                if music_on:
                    try:
                        pygame.mixer.music.unpause()
                    except Exception:
                        pass
                else:
                    try:
                        pygame.mixer.music.pause()
                    except Exception:
                        pass

            if (finger_x and finger_y and sfx_rect.collidepoint(finger_x, finger_y)) or (sfx_rect.collidepoint(mx, my) and clicked):
                sfx_on = not sfx_on

            if (finger_x and finger_y and back_rect.collidepoint(finger_x, finger_y)) or (back_rect.collidepoint(mx, my) and clicked):
                game_state = "menu"

        elif game_state == "shop":
            title = font.render("Shop", True, (255, 255, 255))
            screen.blit(title, ((width - title.get_width()) // 2, 40))

            # Define shop items
            shop_items = [
                {"id": "trail_neon", "name": "Trail Neon", "price": 5, "desc": "Neon blue swipe trail"},
                {"id": "trail_rainbow", "name": "Trail Rainbow", "price": 8, "desc": "Colorful rainbow swipe trail"},
            ]

            # draw items as cards
            card_w = 420
            card_h = 120
            cx = (width - card_w) // 2
            for idx, item in enumerate(shop_items):
                cy = 120 + idx * (card_h + 18)
                rect = pygame.Rect(cx, cy, card_w, card_h)
                pygame.draw.rect(screen, (30, 30, 30), rect, border_radius=8)

                # item title and description
                it_name = font.render(item["name"], True, (255, 240, 180))
                screen.blit(it_name, (rect.x + 12, rect.y + 10))
                it_desc = small_font.render(item["desc"], True, (200, 200, 200))
                screen.blit(it_desc, (rect.x + 12, rect.y + 44))

                # Price - use a smaller font and align vertically with the button
                price_txt = tiny_font.render(f"{item['price']}", True, (255, 255, 255))

                # Buy / Select button (aligned to right)
                btn_w_local = 96
                btn_h_local = 36
                btn_rect = pygame.Rect(rect.right - 12 - btn_w_local, rect.y + 64, btn_w_local, btn_h_local)
                owned = (item["id"] in purchased_items)
                btn_color = (40, 160, 40) if owned else (80, 80, 180)
                pygame.draw.rect(screen, btn_color, btn_rect, border_radius=6)

                # price positioned to the left of the button with small gap, vertically centered
                price_x = btn_rect.x - 8 - price_txt.get_width()
                price_y = btn_rect.y + (btn_rect.h - price_txt.get_height()) // 2
                screen.blit(price_txt, (price_x, price_y))

                # button label: use tiny font and center it in the button
                btn_label = "Select" if owned else "Buy"
                label_surf = tiny_font.render(btn_label, True, (255, 255, 255))
                label_x = btn_rect.x + (btn_rect.w - label_surf.get_width()) // 2
                label_y = btn_rect.y + (btn_rect.h - label_surf.get_height()) // 2
                screen.blit(label_surf, (label_x, label_y))

                # handle touch/click
                if (finger_x and finger_y and btn_rect.collidepoint(finger_x, finger_y)) or (btn_rect.collidepoint(mx, my) and clicked):
                    # buy flow
                    if not owned:
                        if coin_count >= item["price"]:
                            coin_count -= item["price"]
                            purchased_items.add(item["id"])
                            try:
                                save_coin_count()
                            except Exception:
                                pass
                            shop_msg = {"text": f"Bought {item['name']}!", "age": 0, "life": 90}
                        else:
                            shop_msg = {"text": "Not enough coins", "age": 0, "life": 60}
                    else:
                        # select owned item
                        globals()["selected_trail"] = item["id"].replace("trail_", "")
                        try:
                            save_coin_count()
                        except Exception:
                            pass
                        shop_msg = {"text": f"Selected {item['name']}", "age": 0, "life": 60}

            # back button at bottom
            back_rect = pygame.Rect(btn_x, height - 92, btn_w, btn_h)
            pygame.draw.rect(screen, (80, 80, 80), back_rect, border_radius=8)
            back_txt = font.render("Back", True, (255, 255, 255))
            screen.blit(back_txt, (back_rect.x + (back_rect.w - back_txt.get_width()) // 2, back_rect.y + 12))
            if (finger_x and finger_y and back_rect.collidepoint(finger_x, finger_y)) or (back_rect.collidepoint(mx, my) and clicked):
                game_state = "menu"

        # (scrolling UI removed)

    # Update dan gambar buah
    for fruit in fruits[:]:
        fruit["x"] += fruit["vx"]
        fruit["y"] += fruit["vy"]
        fruit["vy"] += 1  # gravitasi

        screen.blit(fruit["img"], (fruit["x"], fruit["y"]))

        # Deteksi slice
        if finger_x and finger_y:
            fx, fy = fruit["x"] + 40, fruit["y"] + 40
            dist = math.hypot(fx - finger_x, fy - finger_y)
            if dist < 40:
                # mainkan suara split (hanya saat buah benar-benar terbelah)
                try:
                    if split_sound and sfx_on:
                        split_sound.play()
                    elif slash_sound and sfx_on:
                        # fallback jika split_sound tidak tersedia
                        slash_sound.play()
                except Exception:
                    pass
                # buat efek cipratan jus sesuai jenis buah
                try:
                    # sample a representative color from the fruit image (center area)
                    try:
                        img_surf = fruit.get("img")
                        if img_surf:
                            iw, ih = img_surf.get_width(), img_surf.get_height()
                            # sample a small patch around the center to average (robust to borders)
                            sx = max(0, iw // 2 - 3)
                            sy = max(0, ih // 2 - 3)
                            sw = min(6, iw - sx)
                            sh = min(6, ih - sy)
                            try:
                                patch = img_surf.subsurface((sx, sy, sw, sh)).copy()
                                arr = pygame.surfarray.array3d(patch)
                                avg = arr.mean(axis=(0, 1)).astype(int)
                                c = (int(avg[0]), int(avg[1]), int(avg[2]))
                            except Exception:
                                # fallback to center pixel if surfarray/subsurface fails
                                try:
                                    r, g, b, a = img_surf.get_at((min(iw-1, iw//2), min(ih-1, ih//2)))
                                    c = (r, g, b)
                                except Exception:
                                    c = random.choice([(255, 0, 0), (255, 255, 0), (0, 255, 0), (255, 128, 0)])
                        else:
                            c = random.choice([(255, 0, 0), (255, 255, 0), (0, 255, 0), (255, 128, 0)])
                    except Exception:
                        # final fallback
                        c = random.choice([(255, 0, 0), (255, 255, 0), (0, 255, 0), (255, 128, 0)])
                    fx = fruit["x"] + 40
                    fy = fruit["y"] + 40
                    # spawn several streak particles (radial) for a nicer splash
                    for _ in range(18):
                        ang = random.uniform(0, math.pi * 2)
                        speed = random.uniform(2.5, 8.0)
                        vx = math.cos(ang) * speed
                        vy = math.sin(ang) * speed - random.uniform(0.5, 2.5)
                        life = random.randint(12, 22)
                        x0 = fx + random.uniform(-6, 6)
                        y0 = fy + random.uniform(-6, 6)
                        splashes.append({
                            "x": x0,
                            "y": y0,
                            "vx": vx,
                            "vy": vy,
                            "color": c,
                            "life": life,
                            "max_life": life,
                            # trail points for flowing look (newest first)
                            "trail": [(x0, y0)],
                            "seed": random.uniform(0, 10),
                            "age": 0,
                        })
                    # spawn small glittery particles (spark / fruit bits)
                    try:
                        for _ in range(20):
                            pvx = random.uniform(-3.0, 3.0)
                            pvy = random.uniform(-5.0, -1.0)
                            life = random.randint(18, 36)
                            size = random.randint(2, 6)
                            particles.append({
                                "x": fx + random.uniform(-6, 6),
                                "y": fy + random.uniform(-6, 6),
                                "vx": pvx,
                                "vy": pvy,
                                "color": c,
                                "life": life,
                                "max_life": life,
                                "size": size,
                                "age": 0,
                            })
                    except Exception:
                        pass
                except Exception:
                    pass
                # buat potongan buah dan tambahkan skor
                split_fruit(fruit)
                if fruit in fruits:
                    fruits.remove(fruit)

                # Combo / multiplier logic
                now = time.time()
                if (now - last_slice_time) <= 0.5:
                    combo_count += 1
                else:
                    combo_count = 1
                last_slice_time = now

                # multiplier rule: start rewarding from 3+ combos
                if combo_count >= 3:
                    multiplier = 2
                else:
                    multiplier = 1

                # add score with multiplier
                score += 1 * multiplier

                # spawn a combo popup ONLY on specific combo milestones: 3,7,11,... (3 + 4n)
                try:
                    if combo_count >= 3 and ((combo_count - 3) % 4) == 0:
                        combo_popups.append({
                            "text": f"COMBO x{combo_count}",
                            "x": fx,
                            "y": fy - 10,
                            "age": 0,
                            "life": 45,
                        })
                        # camera shake and combo lightning for extra impact
                        camera_shake_timer = 14
                        camera_shake_intensity = 8
                        combo_lightning_timer = 14
                        # play thunder/combo sound if available
                        try:
                            if combo_sound and sfx_on:
                                combo_sound.play()
                        except Exception:
                            pass
                except Exception:
                    pass

        # Hilangkan buah di bawah layar
        if fruit["y"] > height + 80:
            if fruit in fruits:
                fruits.remove(fruit)

    # Update dan gambar koin (rare coins)
    for coin in coins[:]:
        coin["x"] += coin.get("vx", 0)
        coin["y"] += coin.get("vy", 0)
        coin["vy"] += 1  # gravity

        # draw coin
        if coin.get("img"):
            try:
                screen.blit(coin["img"], (coin["x"], coin["y"]))
            except Exception:
                pygame.draw.circle(screen, (255, 215, 0), (int(coin["x"] + 16), int(coin["y"] + 16)), 14)
        else:
            pygame.draw.circle(screen, (255, 215, 0), (int(coin["x"] + 16), int(coin["y"] + 16)), 14)

        # detect slice
        if finger_x and finger_y:
            cx = coin["x"] + (coin.get("img").get_width() // 2 if coin.get("img") else 16)
            cy = coin["y"] + (coin.get("img").get_height() // 2 if coin.get("img") else 16)
            d = math.hypot(cx - finger_x, cy - finger_y)
            if d < 36:
                # play split or coin-specific sound
                try:
                    if split_sound and sfx_on:
                        split_sound.play()
                except Exception:
                    pass

                # sample a representative color from the coin image
                try:
                    img_surf = coin.get("img")
                    if img_surf:
                        iw, ih = img_surf.get_width(), img_surf.get_height()
                        sx = max(0, iw // 2 - 2)
                        sy = max(0, ih // 2 - 2)
                        sw = min(4, iw - sx)
                        sh = min(4, ih - sy)
                        try:
                            patch = img_surf.subsurface((sx, sy, sw, sh)).copy()
                            arr = pygame.surfarray.array3d(patch)
                            avg = arr.mean(axis=(0, 1)).astype(int)
                            cc = (int(avg[0]), int(avg[1]), int(avg[2]))
                        except Exception:
                            r, g, b, a = img_surf.get_at((min(iw - 1, iw // 2), min(ih - 1, ih // 2)))
                            cc = (r, g, b)
                    else:
                        cc = (255, 215, 0)
                except Exception:
                    cc = (255, 215, 0)

                # spawn several particles that travel toward the coin UI (top-right)
                target_x = width - 48 - 12
                target_y = 12 + 12
                for _ in range(14):
                    # start near the coin center
                    px = cx + random.uniform(-6, 6)
                    py = cy + random.uniform(-6, 6)
                    # compute direction toward UI target
                    dx = target_x - px
                    dy = target_y - py
                    dist = max(1.0, math.hypot(dx, dy))
                    # initial velocity toward target plus some jitter
                    speed = random.uniform(4.0, 9.0)
                    pvx = (dx / dist) * speed + random.uniform(-1.5, 1.5)
                    pvy = (dy / dist) * speed + random.uniform(-1.5, 1.5)
                    life = random.randint(28, 48)
                    size = random.randint(2, 6)
                    particles.append({
                        "x": px,
                        "y": py,
                        "vx": pvx,
                        "vy": pvy,
                        "color": cc,
                        "life": life,
                        "max_life": life,
                        "size": size,
                        "age": 0,
                        # visual-only: these particles head to UI; coin count already incremented
                        "to_ui": True,
                    })

                # increment coin counter and give a score bonus that respects the
                # current multiplier. Coins double the base slice value.
                try:
                    coin_count += 1
                    # persist immediately so closing the game keeps progress
                    try:
                        save_coin_count()
                    except Exception:
                        pass
                except Exception:
                    coin_count = coin_count if 'coin_count' in globals() else 0
                    coin_count += 1
                    try:
                        save_coin_count()
                    except Exception:
                        pass
                try:
                    # base slice point is 1; coin gives 2x that, and multiplier applies
                    coin_score = int(1 * 2 * max(1, multiplier))
                    score += coin_score
                except Exception:
                    pass

                # optional visual popup near UI (small transient)
                try:
                    combo_popups.append({
                        "text": f"+COIN",
                        "x": target_x,
                        "y": target_y + 12,
                        "age": 0,
                        "life": 30,
                    })
                except Exception:
                    pass

                # remove coin safely
                if coin in coins:
                    coins.remove(coin)

        # remove coin if it falls below the screen
        if coin["y"] > height + 120:
            if coin in coins:
                coins.remove(coin)

    # Update dan gambar obstacles (anomali)
    for obs in obstacles[:]:
        obs["x"] += obs["vx"]
        obs["y"] += obs["vy"]
        obs["vy"] += 1  # gravity

        # draw obstacle (use image if available)
        if obs.get("img"):
            try:
                screen.blit(obs["img"], (obs["x"], obs["y"]))
            except Exception:
                # fallback to simple circle
                pygame.draw.circle(screen, (220, 80, 80), (int(obs["x"] + 16), int(obs["y"] + 16)), 18)
        else:
            pygame.draw.circle(screen, (220, 80, 80), (int(obs["x"] + 16), int(obs["y"] + 16)), 18)

        # detect slice by finger
        if finger_x and finger_y:
            ox_c = obs["x"] + (obs.get("img").get_width() // 2 if obs.get("img") else 16)
            oy_c = obs["y"] + (obs.get("img").get_height() // 2 if obs.get("img") else 16)
            d = math.hypot(ox_c - finger_x, oy_c - finger_y)
            if d < 36:
                # sample color from obstacle image if possible
                try:
                    img_surf = obs.get("img")
                    if img_surf:
                        iw, ih = img_surf.get_width(), img_surf.get_height()
                        sx = max(0, iw // 2 - 3)
                        sy = max(0, ih // 2 - 3)
                        sw = min(6, iw - sx)
                        sh = min(6, ih - sy)
                        try:
                            patch = img_surf.subsurface((sx, sy, sw, sh)).copy()
                            arr = pygame.surfarray.array3d(patch)
                            avg = arr.mean(axis=(0, 1)).astype(int)
                            oc = (int(avg[0]), int(avg[1]), int(avg[2]))
                        except Exception:
                            r, g, b, a = img_surf.get_at((min(iw-1, iw//2), min(ih-1, ih//2)))
                            oc = (r, g, b)
                    else:
                        oc = (255, 200, 60)
                except Exception:
                    oc = (255, 200, 60)


                # spawn local explosion particles that scatter (non-sticky)
                local_life = 60  # local particles live ~2s
                for _ in range(80):
                    ang = random.uniform(0, math.pi * 2)
                    spd = random.uniform(3.0, 14.0)
                    pvx = math.cos(ang) * spd
                    pvy = math.sin(ang) * spd - random.uniform(0.5, 4.0)
                    life = random.randint(int(local_life * 0.7), int(local_life * 1.2))
                    size = random.randint(2, 8)
                    px = ox_c + random.uniform(-8, 8)
                    py = oy_c + random.uniform(-8, 8)
                    particles.append({
                        "x": px,
                        "y": py,
                        "vx": pvx,
                        "vy": pvy,
                        "color": oc,
                        "life": life,
                        "max_life": life,
                        "size": size,
                        "age": 0,
                    })

                # spawn a single precomputed full-screen splatter overlay (3 seconds)
                try:
                    spl_life = 90  # 3 seconds at 30fps
                    blobs = []
                    # choose number of blobs proportional to screen area but cap for perf
                    blob_count = min(220, max(80, int((width * height) / 12000)))
                    for _b in range(blob_count):
                        bx = random.uniform(0, width)
                        by = random.uniform(0, height)
                        br = random.randint(6, 48)
                        balpha = random.randint(40, 200)
                        blobs.append((bx, by, br, balpha))
                    screen_splatters.append({"age": 0, "life": spl_life, "color": oc, "blobs": blobs})
                except Exception:
                    pass

                # add shockwave and flash
                shockwaves.append({"x": ox_c, "y": oy_c, "age": 0, "life": 30, "max_r": 240})
                explosion_flash_timer = 12

                # camera shake to emphasize the explosion
                camera_shake_timer = 45
                camera_shake_intensity = 14

                # play explosion sound and penalize score
                try:
                    if boom_explosion_sound and sfx_on:
                        boom_explosion_sound.play()
                    elif boom_sound and sfx_on:
                        boom_sound.play()
                except Exception:
                    pass

                # deduct score penalty for slicing a boom
                try:
                    score -= 10
                except Exception:
                    # should not happen, but ignore if score not writable in scope
                    pass

                # remove obstacle safely
                if obs in obstacles:
                    obstacles.remove(obs)

        # remove obstacle if off-screen
        if obs["y"] > height + 120:
            if obs in obstacles:
                obstacles.remove(obs)

    # Update dan gambar potongan buah (halves)
    for half in halves[:]:
        half["x"] += half["vx"]
        half["y"] += half["vy"]
        half["vy"] += 0.8  # gravitasi lebih ringan untuk efek

        half["angle"] += half["avel"]
        half["life"] -= 1

        # alpha menurun seiring life tersisa
        if half.get("max_life"):
            alpha = int(255 * (half["life"] / half["max_life"]))
        else:
            alpha = int(255 * (half["life"] / 45))
        half["alpha"] = max(0, min(255, alpha))

        # gambar rotated dengan alpha
        rotated = pygame.transform.rotate(half["img"], half["angle"])
        rotated.set_alpha(half["alpha"])  # set overall transparency

        # pusat gambar (treat half['x'],half['y'] as top-left of original half image)
        img_w, img_h = half["img"].get_width(), half["img"].get_height()
        center_x = half["x"] + img_w / 2
        center_y = half["y"] + img_h / 2
        rect = rotated.get_rect(center=(center_x, center_y))
        screen.blit(rotated, rect.topleft)

        # hapus saat life habis atau sudah jauh ke bawah
        if half["life"] <= 0 or half["alpha"] <= 0 or half["y"] > height + 120:
            if half in halves:
                halves.remove(half)

    # Update and draw splashes (streak particles) onto a single alpha surface
    if splashes:
        splash_surf = pygame.Surface((width, height), pygame.SRCALPHA)
        for s in splashes[:]:
            try:
                # physics
                s["x"] += s["vx"]
                s["y"] += s["vy"]
                s["vy"] += 0.3
                s["age"] += 1

                # append to trail (newest first)
                s["trail"].insert(0, (s["x"], s["y"]))
                if len(s["trail"]) > 12:
                    s["trail"].pop()

                ratio = max(0.0, s["life"] / float(s.get("max_life", 1)))

                # draw tapered segments along the trail with slight curvature (perpendicular wobble)
                for j in range(len(s["trail"]) - 1):
                    (x1f, y1f) = s["trail"][j]
                    (x2f, y2f) = s["trail"][j + 1]

                    # perpendicular wobble based on seed+age+j to make the flow organic
                    dx = x2f - x1f
                    dy = y2f - y1f
                    seg_len = math.hypot(dx, dy) + 1e-6
                    px = -dy / seg_len
                    py = dx / seg_len
                    wobble = math.sin((s["age"] * 0.25) + s.get("seed", 0) + j) * (3.0 * (1 - j / len(s["trail"])))
                    ox1 = x1f + px * wobble
                    oy1 = y1f + py * wobble
                    ox2 = x2f + px * wobble
                    oy2 = y2f + py * wobble

                    # alpha tapers along the trail
                    t = 1.0 - (j / float(max(1, len(s["trail"]) - 1)))
                    alpha = int(255 * ratio * t)
                    col = (s["color"][0], s["color"][1], s["color"][2], alpha)
                    thickness = max(1, int(6 * t * ratio))
                    pygame.draw.line(splash_surf, col, (int(ox1), int(oy1)), (int(ox2), int(oy2)), thickness)

                s["life"] -= 1
                if s["life"] <= 0:
                    splashes.remove(s)
            except Exception:
                try:
                    splashes.remove(s)
                except Exception:
                    pass
        # blit all splashes once
        screen.blit(splash_surf, (0, 0))

    # Update and draw small particles (spark / fruit bits)
    if particles:
        try:
            for p in particles[:]:
                # particle movement
                if p.get("to_ui"):
                    # particles heading to UI: home toward top-right coin icon
                    target_x = width - 48 - 12
                    target_y = 12 + 12
                    dx = target_x - p["x"]
                    dy = target_y - p["y"]
                    dist = max(1.0, math.hypot(dx, dy))
                    # desired speed slows as it approaches
                    desired_speed = max(2.0, dist * 0.08)
                    dir_x = dx / dist
                    dir_y = dy / dist
                    # gentle steering toward target
                    p["vx"] = p.get("vx", 0) * 0.86 + dir_x * desired_speed * 0.14
                    p["vy"] = p.get("vy", 0) * 0.86 + dir_y * desired_speed * 0.14
                    p["x"] += p.get("vx", 0)
                    p["y"] += p.get("vy", 0)
                    p["age"] = p.get("age", 0) + 1
                    # remove quickly if reached UI
                    if math.hypot(target_x - p["x"], target_y - p["y"]) < 12:
                        try:
                            particles.remove(p)
                        except Exception:
                            pass
                        continue
                else:
                    # normal physics (particles scatter)
                    p["x"] += p.get("vx", 0)
                    p["y"] += p.get("vy", 0)
                    # small gravity for bits
                    p["vy"] = p.get("vy", 0) + 0.18
                    p["age"] = p.get("age", 0) + 1

                # fade out based on life
                ratio = max(0.0, p.get("life", 1) / float(max(1, p.get("max_life", 1))))
                alpha = int(255 * ratio)

                # draw a small circle with alpha onto a temp surface
                sz = max(1, int(p.get("size", 3)))
                surf = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
                col = p.get("color", (255, 255, 255))
                try:
                    pygame.draw.circle(surf, (col[0], col[1], col[2], alpha), (sz, sz), sz)
                    screen.blit(surf, (int(p["x"] - sz), int(p["y"] - sz)))
                except Exception:
                    pass

                p["life"] = p.get("life", 0) - 1
                # normal particles removed when life ends or off-screen
                if p["life"] <= 0 or p["y"] > height + 240 or p["x"] < -60 or p["x"] > width + 60:
                    try:
                        particles.remove(p)
                    except Exception:
                        pass
        except Exception:
            # defensive: clear if something unexpected happens
            try:
                particles.clear()
            except Exception:
                pass

    # Draw any full-screen splatter overlays (fade over their life)
    if screen_splatters:
        for spl in screen_splatters[:]:
            try:
                age = spl.get("age", 0)
                life = float(max(1, spl.get("life", 1)))
                t = age / life
                alpha_mul = max(0.0, 1.0 - t)

                overlay = pygame.Surface((width, height), pygame.SRCALPHA)
                base_col = spl.get("color", (255, 200, 60))

                # draw precomputed blobs with alpha scaled by remaining life
                for (bx, by, br, balpha) in spl.get("blobs", []):
                    a = int(balpha * alpha_mul)
                    try:
                        pygame.draw.circle(overlay, (base_col[0], base_col[1], base_col[2], a), (int(bx), int(by)), int(br))
                    except Exception:
                        pass

                screen.blit(overlay, (0, 0))

                spl["age"] = age + 1
                if spl["age"] >= spl.get("life", 1):
                    try:
                        screen_splatters.remove(spl)
                    except Exception:
                        pass
            except Exception:
                try:
                    screen_splatters.remove(spl)
                except Exception:
                    pass

    # Lightning overlay ketika lightning_timer > 0
    if lightning_timer > 0 and len(finger_trail) > 1:
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        # draw several jittered lines to simulate glow
        for j in range(3):
            alpha = max(40, 200 - j * 70)
            col = (180, 220, 255, alpha)
            width_line = 6 - j * 2
            points = []
            for (px, py) in finger_trail:
                # add small random jitter per layer for a more electric look
                jitter_x = px + random.uniform(-6 + j * 2, 6 - j * 2)
                jitter_y = py + random.uniform(-6 + j * 2, 6 - j * 2)
                points.append((int(jitter_x), int(jitter_y)))
            if len(points) > 1:
                pygame.draw.lines(overlay, col, False, points, max(1, width_line))

        # bright center line
        center_col = (245, 255, 255, 230)
        pygame.draw.lines(overlay, center_col, False, finger_trail, 2)

        screen.blit(overlay, (0, 0))
        lightning_timer -= 1

    # Combo-triggered lightning (bigger flash) when combo_lightning_timer > 0
    if combo_lightning_timer > 0:
        try:
            flash = pygame.Surface((width, height), pygame.SRCALPHA)
            alpha = int(220 * (combo_lightning_timer / 14.0))
            flash.fill((255, 255, 255, alpha))
            # jittered streaks for dramatic effect
            for i in range(6):
                pts = []
                x = random.randint(0, width // 4)
                for sx in range(0, width, max(40, random.randint(30, 80))):
                    pts.append((sx + random.randint(-20, 20), random.randint(0, height)))
                col = (200, 230, 255, max(20, alpha - i * 30))
                pygame.draw.lines(flash, col, False, pts, max(1, 6 - i))
            screen.blit(flash, (0, 0))
        except Exception:
            pass
        combo_lightning_timer -= 1

    # Draw combo popups (animated: pop -> float -> fade) with glow and shadow
    if combo_popups:
        for p in combo_popups[:]:
            p["age"] += 1
            life = float(p.get("life", 30))
            age = float(p["age"])
            t = age / life
            # ratio goes from 1 -> 0 as it ages; use to compute alpha and scale
            ratio = max(0.0, 1.0 - t)
            alpha = int(255 * ratio)

            try:
                text = p.get("text", "")

                # scale: pop at start then slowly shrink while floating
                scale = 1.0 + 0.9 * max(0.0, (1.0 - t))

                base_surf = combo_font.render(text, True, (255, 245, 120))
                # shadow
                shadow = combo_font.render(text, True, (10, 10, 10))

                # apply scale via smoothscale
                bw, bh = base_surf.get_size()
                sw = max(1, int(bw * scale))
                sh = max(1, int(bh * scale))
                base_scaled = pygame.transform.smoothscale(base_surf, (sw, sh)).convert_alpha()
                shadow_scaled = pygame.transform.smoothscale(shadow, (sw, sh)).convert_alpha()

                # set alpha
                base_scaled.set_alpha(alpha)
                shadow_scaled.set_alpha(max(0, alpha - 80))

                # position (float up while fading)
                y_off = -int((1.0 - ratio) * 60)
                cx = int(p.get("x", width // 2))
                cy = int(p.get("y", height // 2)) + y_off

                # draw soft glow by drawing slightly larger translucent layers
                for glow_i, glow_alpha in ((1, int(alpha * 0.18)), (2, int(alpha * 0.12)), (3, int(alpha * 0.08))):
                    try:
                        glow = pygame.transform.smoothscale(base_surf, (max(1, int(sw * (1.0 + glow_i * 0.08))), max(1, int(sh * (1.0 + glow_i * 0.08))))).convert_alpha()
                        glow.set_alpha(glow_alpha)
                        gx = cx - glow.get_width() // 2
                        gy = cy - glow.get_height() // 2
                        screen.blit(glow, (gx, gy))
                    except Exception:
                        pass

                # shadow (slightly offset)
                sx = cx - shadow_scaled.get_width() // 2 + 3
                sy = cy - shadow_scaled.get_height() // 2 + 3
                screen.blit(shadow_scaled, (sx, sy))

                # main text
                tx = cx - base_scaled.get_width() // 2
                ty = cy - base_scaled.get_height() // 2
                screen.blit(base_scaled, (tx, ty))
            except Exception:
                pass

            if p["age"] >= p.get("life", 30):
                try:
                    combo_popups.remove(p)
                except Exception:
                    pass

    # Tampilkan skor
    text = font.render(f"Score: {score}", True, (255, 255, 255))
    screen.blit(text, (10, 10))
    # show multiplier badge if active
    if multiplier > 1:
        mul_text = small_font.render(f"x{multiplier}", True, (255, 200, 60))
        screen.blit(mul_text, (10 + text.get_width() + 8, 14))

    # Draw coin UI at top-right
    try:
        margin = 12
        if coin_img:
            cw = coin_img.get_width()
            ch = coin_img.get_height()
            coin_x = width - margin - cw
            coin_y = margin
            # blit coin image
            screen.blit(coin_img, (coin_x, coin_y))
            # render count left of coin; center vertically with the coin image
            cnt_text = font.render(str(coin_count), True, (255, 255, 255))
            cnt_x = coin_x - 10 - cnt_text.get_width()
            cnt_y = coin_y + (ch - cnt_text.get_height()) // 2
            screen.blit(cnt_text, (cnt_x, cnt_y))
        else:
            # fallback simple icon
            coin_x = width - margin - 28
            coin_y = margin
            pygame.draw.circle(screen, (255, 215, 0), (coin_x + 14, coin_y + 14), 14)
            cnt_text = font.render(str(coin_count), True, (255, 255, 255))
            cnt_x = coin_x - 10 - cnt_text.get_width()
            cnt_y = coin_y + (28 - cnt_text.get_height()) // 2
            screen.blit(cnt_text, (cnt_x, cnt_y))
    except Exception:
        pass
    pygame.display.flip()
    clock.tick(30)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

cap.release()
try:
    # final save before exit
    try:
        save_coin_count()
    except Exception:
        pass
except Exception:
    pass
pygame.quit()
