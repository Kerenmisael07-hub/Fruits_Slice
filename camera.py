import cv2
import mediapipe as mp
import pygame
import random
import math

# --- Inisialisasi MediaPipe ---
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands(max_num_hands=1)
cap = cv2.VideoCapture(0)

# --- Inisialisasi Pygame ---
pygame.init()
width, height = 800, 600
screen = pygame.display.set_mode((width, height))
pygame.display.set_caption("🍉 Fruit Slice by Misael")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)

# --- Kelas Buah ---
class Fruit:
    def __init__(self):
        self.x = random.randint(50, width - 50)
        self.y = height
        self.speed = random.randint(5, 10)
        self.size = 40
        self.color = (random.randint(200, 255), random.randint(0, 50), random.randint(0, 50))
        self.alive = True

    def update(self):
        self.y -= self.speed
        if self.y < -50:
            self.alive = False

    def draw(self):
        pygame.draw.circle(screen, self.color, (self.x, self.y), self.size)

# --- Variabel Game ---
fruits = []
score = 0
running = True

# --- Loop Utama Game ---
while running:
    success, img = cap.read()
    img = cv2.flip(img, 1)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Tambah buah baru secara acak
    if random.random() < 0.02:
        fruits.append(Fruit())

    # Deteksi jari telunjuk
    finger_pos = None
    if results.multi_hand_landmarks:
        for handLms in results.multi_hand_landmarks:
            lm = handLms.landmark[8]  # ujung jari telunjuk
            h, w, _ = img.shape
            finger_pos = (int(lm.x * width), int(lm.y * height))
            mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)

    # Gambar background
    screen.fill((30, 30, 30))

    # Update dan gambar semua buah
    for fruit in fruits[:]:
        fruit.update()
        fruit.draw()

        # Jika jari kena buah
        if finger_pos:
            dist = math.hypot(fruit.x - finger_pos[0], fruit.y - finger_pos[1])
            if dist < fruit.size:
                fruits.remove(fruit)
                score += 1

        if not fruit.alive:
            fruits.remove(fruit)

    # Tampilkan skor
    text = font.render(f"Score: {score}", True, (255, 255, 255))
    screen.blit(text, (10, 10))

    pygame.display.flip()
    clock.tick(30)

# --- Selesai ---
cap.release()
cv2.destroyAllWindows()
pygame.quit()
