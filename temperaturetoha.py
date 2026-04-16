import json
import serial
import time
from datetime import datetime
import pytz
import paho.mqtt.client as mqtt
import board
import adafruit_dht

# UART-por Raspberry Pi (TX/RX)
SERIAL_PORT = "/dev/serial0"  # can be /dev/ttyAMA0 or /dev/ttyS0 depending on configuration
BAUDRATE = 9600
TIMEZONE = pytz.timezone("Europe/Helsinki")

MQTT_BROKER = "0.0.0.0"      # MQTT-broker IP
MQTT_PORT = 1883                  # default port
MQTT_TOPIC = "sensors/mhz19b"     # mqtt topic
MQTT_CLIENT_ID = "raspberry_sender"
MQTT_USERNAME = "someusername"              # username 
MQTT_PASSWORD = "somepasswd"              # password
DISCOVERY_PREFIX = "homeassistant"

# MH-Z19B data
MHZ19_OBJECT_ID = "raspi-mhz19b"
MHZ19_STATE_TOPIC = f"sensors/{MHZ19_OBJECT_ID}/state"
MHZ19_DEVICE_NAME = "MHZ19B Sensor"

# DHT22 data
DHT_OBJECT_ID = "raspi-dht22"
DHT_STATE_TOPIC = f"sensors/{DHT_OBJECT_ID}/state"
DHT_DEVICE_NAME = "DHT22 Sensor"
DHT_PIN = 4   # GPIO-pin DHT22 DATA
last_dht_temperature = None
last_dht_humidity = None

def current_time():
    now = datetime.now()
    return now.strftime("%Y-%m-%dT%H:%M:%S%z")

def read_mhz19b():
    try:
        with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1) as ser:
            # Send command: CO2-reading
            ser.write(b"\xFF\x01\x86\x00\x00\x00\x00\x00\x79")
            r = ser.read(9)

            if len(r) == 9 and r[0] == 0xff and r[1] == 0x86:
                # CO2-value in first two databytes
                return {"time": current_time(),
                    "co2": r[2]*256 + r[3],
                    "temperature": r[4] - 40,
                    "TT": r[4], # raw temperature
                    "SS": r[5], # status?
                    "Uh": r[6], # ticks in calibration cycle?
                    "Ul": r[7]} # number of performed calibrations?
            else:
                raise Exception("got unexpected answer %s" % r)
    except Exception as e:
        print("Exception:", e)
    return None

dht_sensor = adafruit_dht.DHT22(board.D4, use_pulseio=False)

def read_dht22():
    global last_dht_temperature, last_dht_humidity

    for attempt in range(1):   # 5 attemts
        try:
            temperature_c = dht_sensor.temperature
            humidity = dht_sensor.humidity

            # --- FIX TEMPERATURE (-0.3 °C) ---
            if temperature_c is not None:
                temperature_c += 0.3

            #print("RAW:", dht_sensor.temperature, dht_sensor.humidity)
            # Check for valid data
            if temperature_c is not None and humidity is not None:
                temperature_c = round(temperature_c, 1)
                humidity = round(humidity, 1)
                temperature_c = round(temperature_c, 1)
                humidity = round(humidity, 1)

            if last_dht_temperature is not None:
                if abs(temperature_c - last_dht_temperature) > 5:
                    print(f"DHT22 jump rejected: {temperature_c} (prev {last_dht_temperature})")
                    raise ValueError("Temperature jump")

            if last_dht_humidity is not None:
                if abs(humidity - last_dht_humidity) > 10:
                    print(f"DHT22 humidity jump rejected: {humidity} (prev {last_dht_humidity})")
                    raise ValueError("Humidity jump")

            # Save last successful reading
            last_dht_temperature = temperature_c
            last_dht_humidity = humidity

            return {
                "temperature": temperature_c,
                "humidity": humidity
            }

        except Exception as e:
            print(f"DHT22 read error ({attempt+1}/5):", e)
            time.sleep(2.0)  # Small delay, try again

    # If no valid value use last valid one
    print("DHT22 failed repeatedly – using last known values.")

    return {
        "temperature": last_dht_temperature,
        "humidity": last_dht_humidity
    }

# ============================
# DISCOVERY -HELPER function
# ============================

def publish_discovery_sensor(client, object_id, device_name, key, name, state_topic, unit=None, device_class=None, state_class=None):
    config_topic = f"{DISCOVERY_PREFIX}/sensor/{object_id}/{key}/config"
    payload = {
        "name": name,
        "unique_id": f"{object_id}_{key}",
        "state_topic": state_topic,
        "value_template": f"{{{{ value_json.{key} }}}}",
        "device": {
            "identifiers": [f"{object_id}_device"],
            "name": device_name
        }
    }
    if unit:
        payload["unit_of_measurement"] = unit
    if device_class:
        payload["device_class"] = device_class
    if state_class:
        payload["state_class"] = state_class

    client.publish(config_topic, json.dumps(payload), retain=True)


def publish_discovery_config(client):
    # ------------------------------
    # MH-Z19B
    # ------------------------------
    publish_discovery_sensor(client, MHZ19_OBJECT_ID, MHZ19_DEVICE_NAME,
                             key="co2", name="MH-Z19B CO₂", state_topic=MHZ19_STATE_TOPIC,
                             unit="ppm", device_class="carbon_dioxide", state_class="measurement")

    publish_discovery_sensor(client, MHZ19_OBJECT_ID, MHZ19_DEVICE_NAME,
                             key="temperature", name="MH-Z19B Temperature",
                             state_topic=MHZ19_STATE_TOPIC, unit="°C", device_class="temperature", state_class="measurement")

    publish_discovery_sensor(client, MHZ19_OBJECT_ID, MHZ19_DEVICE_NAME,
                             key="TT", name="MH-Z19B TT", state_topic=MHZ19_STATE_TOPIC)

    publish_discovery_sensor(client, MHZ19_OBJECT_ID, MHZ19_DEVICE_NAME,
                             key="SS", name="MH-Z19B SS", state_topic=MHZ19_STATE_TOPIC)

    publish_discovery_sensor(client, MHZ19_OBJECT_ID, MHZ19_DEVICE_NAME,
                             key="Uh", name="MH-Z19B Uh", state_topic=MHZ19_STATE_TOPIC)

    publish_discovery_sensor(client, MHZ19_OBJECT_ID, MHZ19_DEVICE_NAME,
                             key="Ul", name="MH-Z19B Ul", state_topic=MHZ19_STATE_TOPIC)

    # ------------------------------
    # DHT22
    # ------------------------------
    publish_discovery_sensor(client, DHT_OBJECT_ID, DHT_DEVICE_NAME,
                             key="temperature", name="DHT22 Temperature",
                             state_topic=DHT_STATE_TOPIC, unit="°C", device_class="temperature", state_class="measurement")

    publish_discovery_sensor(client, DHT_OBJECT_ID, DHT_DEVICE_NAME,
                             key="humidity", name="DHT22 Humidity",
                             state_topic=DHT_STATE_TOPIC, unit="%", device_class="humidity", state_class="measurement")


# ============================
# MAIN LOOP
# ============================

def main():
    # 1. Create MQTT client with VERSION2 callback API
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    
    # 2. Set automatic reconnection delays (Paho handles this internally)
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    # --- CALLBACKS (Updated for VERSION2 compliance) ---
    
    # Note: VERSION2 requires 5 arguments: client, userdata, flags, reason_code, properties
    def on_connect(client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            print("Connected to MQTT broker successfully.")
        else:
            print(f"Connection failed with reason code: {reason_code}")

    # Note: Added 'disconnect_flags' to meet the 5-argument requirement
    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
        # IMPORTANT: Do not use while loops or manual reconnect() here.
        # loop_start() handles reconnection automatically in the background.
        print(f"MQTT disconnected (reason code: {reason_code}). Reconnecting automatically...")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # 3. Set credentials if provided
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # 4. Start the background networking loop before connecting
    client.loop_start()

    # 5. Connect to the broker
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception as e:
        print("ERROR: Initial MQTT broker connection failed:", e)
        # Even if the initial connection fails, loop_start will keep trying in the background
        time.sleep(5)

    # 6. Send Home Assistant discovery configuration
    # Small delay to ensure the connection is established before publishing
    time.sleep(1) 
    publish_discovery_config(client)
    print("Sent Home Assistant discovery configuration.")

    # 7. Main loop for reading sensor data
    try:
        while True:
            # Read and publish MH-Z19B data
            mhz_data = read_mhz19b()
            if mhz_data:
                client.publish(MHZ19_STATE_TOPIC, json.dumps(mhz_data))
                print("MH-Z19B →", mhz_data)

            # Read and publish DHT22 data
            dht_data = read_dht22()
            if dht_data:
                client.publish(DHT_STATE_TOPIC, json.dumps(dht_data))
                print("DHT22 →", dht_data)

            # Wait 5 seconds before the next reading
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("Stopping script...")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
