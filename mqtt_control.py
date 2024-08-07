import paho.mqtt.client as mqtt
import psycopg2
import time
import threading
from datetime import datetime, timedelta

# MQTT settings
broker = "192.168.18.19"
port = 1883
topics = ['cstr-temp', 'cstr-level', 'feed-level', 'ds-tds', 'cstr-temp']

# Database settings
dbname = "sensordata"
user = "postgres"
password = "400220"
host = "localhost"
table = "fo_setting"

# Connect to PostgreSQL database
conn = psycopg2.connect(dbname=dbname, user=user, password=password, host=host)
cursor = conn.cursor()

# MQTT client setup
client = mqtt.Client()

# Global variables for sensor values and previous states
sensor_values = {
    "cstr-temp": None,
    "cstr-level": None,
    "feed-level": None,
    "ds-tds": None
}
previous_states = {
    "cstr/in": None,
    "cstr/heater1": None,
    "cstr/heater2": None,
    "ds/out": None
}
current_settings = {
    "set_cstr_temp": None,
    "hyst_tds": None,
    "set_tds": None
}


# Callback when a message is received
def on_message(client, userdata, message):
    global sensor_values
    sensor_values[message.topic] = float(message.payload.decode("utf-8"))

    # Control logic
    cstr_control()
    feed_control()
    ds_control()

# Function to get settings from database
def get_settings():
    cursor.execute(f"SELECT set_cstr_temp, hyst_tds, set_tds FROM {table} ORDER BY id DESC LIMIT 1")
    return cursor.fetchone()

# Function to update settings
def update_settings():
    global current_settings
    new_settings = get_settings()
    if new_settings:
        current_settings = {
            "set_cstr_temp": new_settings[0],
            "hyst_tds": new_settings[1],
            "set_tds": new_settings[2]
        }
    # Ensure control logic is applied with updated settings
    cstr_control()
    feed_control()
    ds_control()

# Function to publish MQTT messages only on state change
def publish_state(topic, state):
    if previous_states[topic] != state:
        client.publish(topic, state)
        previous_states[topic] = state

# Feed control logic
def feed_control():
    if sensor_values["feed-level"] is not None:
        if sensor_values["feed-level"] <= 20:
            publish_state("cstr/in", "on")
        elif sensor_values["feed-level"] >= 25:
            publish_state("cstr/in", "off")

# CSTR control logic
def cstr_control():
    if current_settings["set_cstr_temp"] is None or sensor_values["cstr-temp"] is None:
        return

    set_cstr_temp = current_settings["set_cstr_temp"]
    if sensor_values["cstr-temp"] < set_cstr_temp:
        publish_state("cstr/heater1", "on")
        publish_state("cstr/heater2", "on")
    else:
        publish_state("cstr/heater1", "off")
        publish_state("cstr/heater2", "off")

# DS control logic
def ds_control():
    if current_settings["set_tds"] is None or current_settings["hyst_tds"] is None or sensor_values["ds-tds"] is None:
        return

    set_tds = current_settings["set_tds"]
    hyst_tds = current_settings["hyst_tds"]
    if sensor_values["ds-tds"] >= set_tds + hyst_tds:
        publish_state("ds/out", "on")
    elif sensor_values["ds-tds"] < set_tds - hyst_tds:
        publish_state("ds/out", "off")

# Periodic status update
def periodic_status_update():
    threading.Timer(120, periodic_status_update).start()  # Schedule the function to run every 2 minutes
    for topic in previous_states:
        if previous_states[topic] is not None:
            client.publish(topic, previous_states[topic])

# Periodic database check
def periodic_db_check():
    threading.Timer(10, periodic_db_check).start()  # Check database every 10 seconds for new settings
    update_settings()

# MQTT connection setup
client.on_message = on_message
client.connect(broker, port)

# Subscribe to topics
for topic in topics:
    client.subscribe(topic)

# Start MQTT loop
client.loop_start()

# Start periodic status updates and database checks
periodic_status_update()
periodic_db_check()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Exiting")
finally:
    client.loop_stop()
    cursor.close()
    conn.close()
