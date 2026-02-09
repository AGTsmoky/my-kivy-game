
import kivy
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.uix.widget import Widget
from kivy.uix.image import Image
from kivy.uix.progressbar import ProgressBar
from kivy.core.audio import SoundLoader
from kivy.graphics import Color, Ellipse # Added for drawing minimap dots
from typing import List
import socket
import threading
import time
import json
import random

kivy.require('2.0.0')

# Game Data (Your character names and everything are here!)
game_data = {
    "characters": {
        "Ijeh": {"ability": "Dash Forward", "moves": ["run", "jump", "shoot"], "design": "Camo"},
        "Obama": {"ability": "Tactical Roll (Backflip)", "moves": ["run", "jump", "shoot", "roll"], "design,
        "Daniel": {"ability": "Sniper Focus", "moves": ["run", "prone", "shoot"], "design": "Ghillie"},
        "Vincent": {"ability": "Heavy Shield", "moves": ["walk", "shield", "shoot"], "design": "Armor"},
        "Ridwan": {"ability": "Silent Steps", "moves": ["run", "crouch", "shoot"], "design": "Ninja"},
        "Sunshine": {"ability": "Med Kit Boost", "moves": ["run", "heal", "shoot"], "design": "Medic"},
        "Messi": {"ability": "Extreme Agility", "moves": ["run_fast", "jump_high", "shoot"], "design": "Spo,
        "Bright": {"ability": "Tech Scan", "moves": ["run", "scan", "shoot"], "design": "Tactical"}
    },
    "guns": {
        "M4A1": {"type": "Assault Rifle"},
        "Sniper": {"type": "Long Range"},
        "Shotgun": {"type": "Close Quarters"},
        "Pistol": {"type": "Sidearm"}
    }
}

# --- Networking Classes ---
class NetworkManager:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn = None

    def host_game_thread(self, success_callback):
        self.sock.bind(('', 5000))
        self.sock.listen(1)
        print("Waiting for a connection...")
        self.conn, addr = self.sock.accept()
        print(f"Connected to {addr}")
        Clock.schedule_once(lambda dt: success_callback())

    def join_game_thread(self, host_ip, success_callback):
        try:
            self.sock.connect((host_ip, 5000))
            self.conn = self.sock
            Clock.schedule_once(lambda dt: success_callback())
        except Exception as e:
            print(f"Connection failed: {e}")

    def send_data(self, data):
        if self.conn:
            try:
                message = json.dumps(data).encode('utf-8')
                self.conn.sendall(message + b'\n')
            except socket.error as e:
                print(f"Send failed: {e}")

    def receive_data_thread(self, update_callback):
        while True:
            if self.conn:
                try:
                    data = self.conn.recv(4096)
                    if data:
                        msg = json.loads(data.decode('utf-8').strip())
                        Clock.schedule_once(lambda dt: update_callback(msg))
                except socket.error:
                    break
                except json.JSONDecodeError:
                    continue

# --- BULLET CLASS ---
class Bullet(Image):
    def __init__(self, side, **kwargs):
        super().__init__(**kwargs)
        self.source = 'bullet.png'
        self.size_hint = (None, None)
        self.size = (16, 8)
        self.side = side
        self.speed = 10 if side == 'player1' else -10

# --- Kivy App Screens ---
class MenuScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        title_text = f"Passion: Local Multiplayer Menu | Select Your Character"
        self.layout.add_widget(Label(text=title_text))

        for char_name in game_data['characters']:
            btn = Button(text=char_name, on_press=self.select_character)
            self.layout.add_widget(btn)

        self.host_btn = Button(text='Host Game (Server)', on_press=self.host_game_pressed, disabled=True)
        self.join_btn = Button(text='Join Game (Client)', on_press=self.join_game_pressed, disabled=True)

        self.layout.add_widget(self.host_btn)
        self.layout.add_widget(self.join_btn)
        self.status_label = Label(text="Please select a character.")
        self.layout.add_widget(self.status_label)
        self.add_widget(self.layout)

    def select_character(self, instance):
        App.get_running_app().player_character_name = instance.text
        self.host_btn.disabled = False
        self.join_btn.disabled = False
        self.status_label.text = f"Selected: {instance.text}. Ready to connect."

    def host_game_pressed(self, instance):
        char_name = App.get_running_app().player_character_name
        thread = threading.Thread(target=App.get_running_app().net_manager.host_game_thread,
                                  args=(self.on_connection_success,))
        thread.daemon = True
        thread.start()
        self.host_btn.text = f"Hosting as {char_name}... (Waiting for Player)"

    def join_game_pressed(self, instance):
        char_name = App.get_running_app().player_character_name
        ip_to_join = "127.0.0.1"
        thread = threading.Thread(target=App.get_running_app().net_manager.join_game_thread,
                                  args=(ip_to_join, self.on_connection_success))
        thread.daemon = True
        thread.start()
        self.join_btn.text = f"Connecting to {ip_to_join} as {char_name}..."

    def on_connection_success(self):
        App.get_running_app().net_manager.send_data({
            "type": "character_selection",
            "character": App.get_running_app().player_character_name
        })
        self.manager.current = 'game'

class GameOverScreen(Screen):
    def __init__(self, winner_name, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=100, spacing=20)
        self.winner_label = Label(text=f'Game Over! \\n {winner_name} Wins!', font_size=40)
        self.restart_btn = Button(text='Back to Menu', on_press=self.back_to_menu)
        layout.add_widget(self.winner_label)
        layout.add_widget(self.restart_btn)
        self.add_widget(layout)

    def back_to_menu(self, instance):
        self.manager.current = 'menu'


class GameScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Add the background image first
        self.background = Image(source='background.png', allow_stretch=True, keep_ratio=False)
        self.add_widget(self.background)

        self.game_layout = Widget()

        # --- Character Data Setup ---
        self.my_char_name = App.get_running_app().player_character_name
        self.opponent_char_name = None
        self.player_speed = 5
        self.bullet_speed_multiplier = 1
        self.ability_active = False
        self.medkit_used = False
        self.is_stealthed = False

        # --- Health Setup ---
        self.player_one_health = 100
        self.player_two_health = 100
        self.damage_amount = 10

        # --- Load Sound Effects ---
        self.sound_shoot = SoundLoader.load('shoot.wav')
        self.sound_hit = SoundLoader.load('hit.wav')
        self.sound_ability = SoundLoader.load('ability.wav')

        # --- UI Elements (Health Bars & Status Labels) ---
        top_bar_layout = BoxLayout(orientation='horizontal', size_hint=(1, None), height=44)
        self.p1_health_bar = ProgressBar(max=100, value=self.player_one_health, size_hint_x=0.4)
        top_bar_layout.add_widget(self.p1_health_bar)
        top_bar_layout.add_widget(Label(text=f'P1: {self.my_char_name}', size_hint_x=0.1))
        self.status_label = Label(text=f'In Game as {self.my_char_name}!', size_hint_x=0.4)
        top_bar_layout.add_widget(self.status_label)
        top_bar_layout.add_widget(Label(text=f'P2: Enemy', size_hint_x=0.1))
        self.p2_health_bar = ProgressBar(max=100, value=self.player_two_health, size_hint_x=0.4)
        top_bar_layout.add_widget(self.p2_health_bar)

        self.add_widget(top_bar_layout)
        self.add_widget(self.game_layout)


        # --- Sprites ---
        self.player_one_sprite = Image(source=f'{self.my_char_name.lower()}.png', pos=(100, 100), size_hint)
        self.player_two_sprite = Image(source=f'messi.png', pos=(500, 100), size_hint=(None, None), size=(6)
        self.game_layout.add_widget(self.player_one_sprite)
        self.game_layout.add_widget(self.player_two_sprite)

        # --- MINIMAP SETUP ---
        self.minimap = Widget(size_hint=(None, None), size=(150, 100), pos=(Window.width - 160, 10))
        with self.minimap.canvas:
            Color(0.1, 0.1, 0.1, 0.8)
            # Draw player 1 dot (red)
            Color(1, 0, 0, 1)
            self.p1_dot = Ellipse(size=(10, 10))
            # Draw player 2 dot (blue)
            Color(0, 0, 1, 1)
            self.p2_dot = Ellipse(size=(10, 10))
        self.add_widget(self.minimap)


        # --- Networking and Game Loop Setup ---
        self.player_one_bullets: List[Bullet] = []
        self.player_two_bullets: List[Bullet] = []
        self._keyboard = Window.request_keyboard(self._keyboard_closed, self)
        self._keyboard.bind(on_key_down=self._on_keyboard_down)
        self._keyboard.bind(on_key_up=self._on_keyboard_up)
        self.pressed_keys = set()
        thread = threading.Thread(target=App.get_running_app().net_manager.receive_data_thread, args=(self.)
        thread.daemon = True
        thread.start()
        Clock.schedule_interval(self.update_game_logic, 1/60.0)
        Clock.schedule_interval(self.send_player_data, 1/10.0)

    def _keyboard_closed(self):
        self._keyboard.unbind(on_key_down=self._on_keyboard_down)
        self._keyboard = None

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        self.pressed_keys.add(text)
        if keycode == 'space':
            self.shoot()
        if text == 'e':
            self.use_ability()
        return True

    def _on_keyboard_up(self, keyboard, keycode):
        if keycode in self.pressed_keys:
            self.pressed_keys.remove(keycode)
        return True

    def use_ability(self):
        if self.ability_active: return
        if self.sound_ability: self.sound_ability.play()

        ability_name = game_data['characters'][self.my_char_name]['ability']

        if self.my_char_name == "Obama":
            self.player_speed *= 3; self.ability_active = True
            Clock.schedule_once(self.deactivate_ability, 2)
        elif self.my_char_name == "Daniel":
            self.damage_amount *= 3; self.bullet_speed_multiplier = 2
            self.ability_active = True
            Clock.schedule_once(self.deactivate_ability, 3)
        elif self.my_char_name == "Vincent":
            self.player_speed = 1; self.ability_active = True
            Clock.schedule_once(self.deactivate_ability, 4)
        elif self.my_char_name == "Sunshine":
            if not self.medkit_used:
                heal_amount = 30
                self.player_one_health = min(100, self.player_one_health + heal_amount)
                self.p1_health_bar.value = self.player_one_health
                self.medkit_used = True
                health_data = {"type": "health_update", "health": self.player_one_health}
                App.get_running_app().net_manager.send_data(health_data)
            else:
                self.status_label.text = "Med Kit already used!"
                return
        elif self.my_char_name == "Ijeh":
            self.player_one_sprite.x += 200; self.status_label.text = "DASH!"
        elif self.my_char_name == "Ridwan":
            if not self.ability_active:
                self.is_stealthed = True; self.player_speed *= 2
                self.ability_active = True
                Clock.schedule_once(self.deactivate_ability, 3)
        elif self.my_char_name == "Messi":
            self.player_speed *= 4; self.status_label.text = "Extreme Agility Active!"
            self.ability_active = True
            Clock.schedule_once(self.deactivate_ability, 5)
        elif self.my_char_name == "Bright":
            self.status_label.text = "Tech Scan Activated! Opponent revealed."
            self.player_two_sprite.opacity = 1
            Clock.unschedule(self.reveal_opponent)

        App.get_running_app().net_manager.send_data({"type": "ability_use", "ability": ability_name, "chara)

    def deactivate_ability(self, dt):
        if self.my_char_name == "Obama": self.player_speed = 5
        elif self.my_char_name == "Daniel": self.damage_amount = 10; self.bullet_speed_multiplier = 1
        elif self.my_char_name == "Vincent": self.player_speed = 5
        elif self.my_char_name == "Ridwan": self.is_stealthed = False; self.player_speed = 5
        elif self.my_char_name == "Messi": self.player_speed = 5

        self.ability_active = False
        self.status_label.text = "Ability deactivated."

    def reveal_opponent(self, dt):
        self.player_two_sprite.opacity = 1
        self.status_label.text = "Opponent revealed!"

    def shoot(self):
        if self.sound_shoot: self.sound_shoot.play()
        bullet = Bullet(side='player1', center=self.player_one_sprite.center)
        bullet.speed *= self.bullet_speed_multiplier
        self.player_one_bullets.append(bullet)
        self.game_layout.add_widget(bullet)
        shoot_data = {"type": "shot", "x": float(bullet.x), "y": float(bullet.y)}
        App.get_running_app().net_manager.send_data(shoot_data)

    def scale_to_minimap(self, x, y):
        map_width = self.minimap.width
        map_height = self.minimap.height
        scale_x = map_width / Window.width
        scale_y = map_height / Window.height
        mini_x = self.minimap.x + (x * scale_x)
        mini_y = self.minimap.y + (y * scale_y)
        return mini_x, mini_y

    def update_game_logic(self, dt):
        # Movement
        if 'w' in self.pressed_keys: self.player_one_sprite.y += self.player_speed
        if 's' in self.pressed_keys: self.player_one_sprite.y -= self.player_speed
        if 'a' in self.pressed_keys: self.player_one_sprite.x -= self.player_speed
        if 'd' in self.pressed_keys: self.player_one_sprite.x += self.player_speed

        # P1 Bullet Logic
        for bullet in list(self.player_one_bullets):
            bullet.x += bullet.speed
            if bullet.x > Window.width or bullet.x < 0: self.remove_bullet(bullet, self.player_one_bullets)
            if bullet.collide_widget(self.player_two_sprite):
                if self.sound_hit: self.sound_hit.play()
                self.remove_bullet(bullet, self.player_one_bullets)

        # P2 Bullet Logic and P1 Collision Check
        for bullet in list(self.player_two_bullets):
            bullet.x += bullet.speed
            if bullet.x > Window.width or bullet.x < 0: self.remove_bullet(bullet, self.player_two_bullets)
            if bullet.collide_widget(self.player_one_sprite):
                if self.my_char_name == "Vincent" and self.ability_active: pass
                else:
                    if self.sound_hit: self.sound_hit.play()
                    self.player_one_health -= self.damage_amount
                    self.p1_health_bar.value = self.player_one_health
                    health_data = {"type": "health_update", "health": self.player_one_health}
                    App.get_running_app().net_manager.send_data(health_data)
                self.remove_bullet(bullet, self.player_two_bullets)

        # Update minimap dot positions every frame
        p1_mini_pos = self.scale_to_minimap(self.player_one_sprite.center_x, self.player_one_sprite.center_)
        self.p1_dot.pos = (p1_mini_pos[0] - 5, p1_mini_pos[1] - 5)
        p2_mini_pos = self.scale_to_minimap(self.player_two_sprite.center_x, self.player_two_sprite.center_)
        self.p2_dot.pos = (p2_mini_pos[0] - 5, p2_mini_pos[1] - 5)

        if self.player_one_health <= 0:
            self.end_game("Player 2")
        elif self.player_two_health <= 0:
            self.end_game("Player 1")

    def end_game(self, winner_name):
        Clock.unschedule(self.update_game_logic)
        Clock.unschedule(self.send_player_data)
        game_over_screen = GameOverScreen(winner_name=winner_name, name='game_over')
        self.manager.add_widget(game_over_screen)
        self.manager.current = 'game_over'

    def remove_bullet(self, bullet, bullet_list):
        if bullet in bullet_list:
            self.game_layout.remove_widget(bullet)
            bullet_list.remove(bullet)

    def update_game_state(self, data):
        if data.get('type') == 'character_selection':
            self.opponent_char_name = data['character']
            self.player_two_sprite.source = f'{self.opponent_char_name.lower()}.png'
        elif data.get('type') == 'shot':
            if self.sound_shoot: self.sound_shoot.play()
            bullet = Bullet(side='player2', pos=(data['x'], data['y']))
            self.player_two_bullets.append(bullet)
            self.game_layout.add_widget(bullet)
        elif data.get('type') == 'health_update':
            self.player_two_health = data['health']
            self.p2_health_bar.value = self.player_two_health
        elif data.get('type') == 'ability_use':
            if self.sound_ability: self.sound_ability.play()
            if data.get('character') == 'Ridwan':
                self.player_two_sprite.opacity = 0
                Clock.schedule_once(self.reveal_opponent, 3)
            elif data.get('character') == 'Bright':
                if self.my_char_name == 'Ridwan':
                    self.player_one_sprite.opacity = 1
        elif data.get('type') == 'stealth_position':
            self.p2_dot.opacity = 0
        elif 'x' in data and 'y' in data and data.get('type') == 'position':
            self.player_two_sprite.pos = (data['x'], data['y'])
            self.p2_dot.opacity = 1

    def send_player_data(self, dt):
        if self.my_char_name == "Ridwan" and self.ability_active:
            self.player_one_sprite.opacity = 0
            self.p1_dot.opacity = 0
            player_data = {"type": "stealth_position"}
        else:
            self.player_one_sprite.opacity = 1
            self.p1_dot.opacity = 1
            player_pos = self.player_one_sprite.pos
            player_data = {"x": float(player_pos), "y": float(player_pos), "type": "position"}
        App.get_running_app().net_manager.send_data(player_data)


class PassionApp(App):
    def build(self):
        self.net_manager = NetworkManager()
        self.player_character_name = None
        Window.clearcolor = (0.1, 0.1, 0.1, 1)
        sm = ScreenManager()
        sm.add_widget(MenuScreen(name='menu'))
        sm.add_widget(GameScreen(name='game'))
        return sm

if __name__ == '__main__':
    PassionApp().run()
