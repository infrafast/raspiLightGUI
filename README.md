# Interactive Menu with an OLED Display and Buttons on Raspberry Pi 5


**Student**: Lennyn Alejandro Castillejo Robles<br>
**Course**: Programmable Systems

This project implements an interactive menu on an `SSD1306` OLED display using a Raspberry Pi 5 running Raspberry Pi OS and Python 3. The menu options are controlled using three physical buttons connected to GPIO pins.

---

## 🛠️ Components Used

- **Raspberry Pi 5 (Raspberry Pi OS)**
- **SSD1306 OLED display (128x64 pixels, I2C protocol)**
- **3 physical buttons**

---

## 🔌 Connections

### 📟 OLED Display (SSD1306)
| OLED | Raspberry Pi 5 pin |
|------|----------|
| VCC  | 3.3V     |
| GND  | GND      |
| SDA  | GPIO2 (physical pin 3) |
| SCL  | GPIO3 (physical pin 5) |

### 🔘 Buttons

| Function | GPIO | Physical pin |
|----------|------|--------------|
| Button 1 (Down) — ◀ / BACK | **GPIO5** | **Pin 29** |
| Button 2 (Select) — OK | **GPIO6** | **Pin 31** |
| Button 3 (Up) — ▶ / NEXT | **GPIO13** | **Pin 33** |
| Button common ground | GND | **Pin 30** or **Pin 34** |

All buttons are configured with an **internal pull-up resistor**. Connect one side
of each button to its GPIO pin and connect their common side to physical GND pin
30 or 34.

---

## 🧠 Program Logic

- A main menu with five options is displayed.
- The display is redrawn only when the selected option changes, improving efficiency.
- When selected, each option displays a different screen for two seconds.
- If **"Exit"** is selected, the program ends.

![image](https://gist.github.com/user-attachments/assets/4b8a4e09-c137-4204-a2e3-6b9fdac8f676)

---

## Installation and execution

```bash
sudo raspi-config nonint do_i2c 0
sudo apt install python3-venv
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
python lightGUI.py
```
## Results
Temperature

![image](https://gist.github.com/user-attachments/assets/0d36a9db-6470-45f6-b7be-c03e97d700be)

Date

![image](https://gist.github.com/user-attachments/assets/5aa0a30f-cd9f-49ff-a5ea-499c112b02c7)

Time
![image](https://gist.github.com/user-attachments/assets/904b9a69-393f-4eb7-9454-fac3ceabc26e)

Wind

![image](https://gist.github.com/user-attachments/assets/6ff67483-eab8-4bb0-8cce-a1a47e569c2a)


Exit

![image](https://gist.github.com/user-attachments/assets/8bdcbab2-b74a-4162-bb02-280558c3259c)
