import paho.mqtt.client as mqtt
import psycopg2
import json
import time
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os
from supabase import create_client, Client

# Load environment variables from .env file
load_dotenv()

# Database configuration
DATABASE_CONFIG = {
    'dbname': 'sensordata',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD'),
    'host': 'localhost',  # Assuming the database is hosted on the Raspberry Pi
    'port': '5432'        # Default PostgreSQL port
}

# MQTT configuration
MQTT_BROKER = '192.168.18.28'
MQTT_PORT = 1883
MQTT_TOPICS = ['cstr-ph', 'feed-ec', 'cstr-orp', 'cstr-temp', 'cstr-level', 
               'feed-level', 'feed-tds', 'feed-temp', 'ds-tds', 'ds-level', 'ds-ec']

# Supabase configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Global variables to store sensor data
sensor_data = {
    'cstr_ph': None,
    'feed_ec': None,
    'cstr_orp': None,
    'cstr_temp': None,
    'cstr_level': None,
    'feed_level': None,
    'feed_tds': None,
    'feed_temp': None,
    'ds_ec': None,
    'ds_tds': None,
    'ds_level': None,
    'vol_to_ds': None,
    'com_vol_fs': None,
    'flux': None,
    'increase_in_fs': None,
    'timestamp': None,
    'published': False
}

# Utility function to convert datetime to string
def datetime_to_str(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None

# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with code {rc}")
    for topic in MQTT_TOPICS:
        client.subscribe(topic)

def on_message(client, userdata, msg):
    global sensor_data
    topic = msg.topic
    payload = json.loads(msg.payload.decode())
    sensor_data['timestamp'] = datetime.now()

    # Update sensor data based on MQTT topic
    if topic == 'cstr-ph':
        sensor_data['cstr_ph'] = float(payload)
    elif topic == 'feed-ec':
        sensor_data['feed_ec'] = float(payload)
    elif topic == 'cstr-orp':
        sensor_data['cstr_orp'] = float(payload)
    elif topic == 'cstr-temp':
        sensor_data['cstr_temp'] = float(payload)
    elif topic == 'cstr-level':
        sensor_data['cstr_level'] = float(payload)
    elif topic == 'feed-level':
        sensor_data['feed_level'] = float(payload)
    elif topic == 'feed-tds':
        sensor_data['feed_tds'] = float(payload)
    elif topic == 'feed-temp':
        sensor_data['feed_temp'] = float(payload)
    elif topic == 'ds-tds':
        sensor_data['ds_tds'] = float(payload)
    elif topic == 'ds-ec':
        sensor_data['ds_ec'] = float(payload)
    elif topic == 'ds-level':
        sensor_data['ds_level'] = float(payload)
    
    # Calculate vol_to_ds, com_vol_fs, flux, and increase_in_fs based on the formulas
    calculate_additional_params()

def calculate_additional_params():
    global sensor_data
    
    # Fetch previous values and ensure they are not None
    previous_feed_level = fetch_previous_feed_level()
    current_feed_level = sensor_data['feed_level']
    if previous_feed_level is not None and current_feed_level is not None:
        sensor_data['vol_to_ds'] = previous_feed_level - current_feed_level
    else:
        sensor_data['vol_to_ds'] = None
    
    # Fetch set init fs and ensure it's not None
    set_init_fs = 20
    if set_init_fs is not None and sensor_data['vol_to_ds'] is not None:
        sensor_data['com_vol_fs'] = set_init_fs - sensor_data['vol_to_ds']
    else:
        sensor_data['com_vol_fs'] = None
    
    # Ensure vol_to_ds is not None before calculating flux
    if sensor_data['vol_to_ds'] is not None:
        sensor_data['flux'] = (sensor_data['vol_to_ds'] * 60) / 5
    else:
        sensor_data['flux'] = None
    
    # Fetch previous feed tds and ensure it's not None
    previous_feed_tds = fetch_previous_feed_tds()
    current_feed_tds = sensor_data['feed_tds']
    if previous_feed_tds is not None and current_feed_tds is not None:
        sensor_data['increase_in_fs'] = current_feed_tds - previous_feed_tds
    else:
        sensor_data['increase_in_fs'] = None

def fetch_previous_feed_level():
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        thirty_seconds_ago = datetime.now() - timedelta(seconds=30)
        query = '''
        SELECT feed_level 
        FROM fo_sensor_data 
        WHERE timestamp <= %s 
        ORDER BY timestamp DESC 
        LIMIT 1;
        '''
        cursor.execute(query, (thirty_seconds_ago,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"Error fetching previous feed level: {e}")
        return None

# def fetch_set_init_fs():
#     try:
#         conn = psycopg2.connect(**DATABASE_CONFIG)
#         cursor = conn.cursor()
#         query = '''
#         SELECT set_init_fs
#         FROM fo_setting 
#         ORDER BY timestamp DESC 
#         LIMIT 1;
#         '''
#         cursor.execute(query)
#         result = cursor.fetchone()
#         cursor.close()
#         conn.close()
#         return result[0] if result else None
#     except Exception as e:
#         print(f"Error fetching set init fs: {e}")
#         return None

def fetch_previous_feed_tds():
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        thirty_seconds_ago = datetime.now() - timedelta(seconds=30)
        query = '''
        SELECT feed_tds 
        FROM fo_sensor_data 
        WHERE timestamp <= %s 
        ORDER BY timestamp DESC 
        LIMIT 1;
        '''
        cursor.execute(query, (thirty_seconds_ago,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"Error fetching previous feed tds: {e}")
        return None

# Function to save data to the PostgreSQL database
def save_to_database(data):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        insert_query = '''
        INSERT INTO fo_sensor_data (timestamp, cstr_ph, feed_ec, cstr_orp, ds_ec, cstr_temp, cstr_level, feed_level, feed_tds, feed_temp, ds_tds, ds_level, vol_to_ds, com_vol_fs, flux, increase_in_fs, published)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        cursor.execute(insert_query, (data['timestamp'], data['cstr_ph'], data['feed_ec'], data['cstr_orp'], data['ds_ec'],
                                     data['cstr_temp'], data['cstr_level'], data['feed_level'], data['feed_tds'], data['feed_temp'], data['ds_tds'], data['ds_level'], data['vol_to_ds'], data['com_vol_fs'], data['flux'], data['increase_in_fs'], data['published']))
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Data saved to database.")
        return True
    except Exception as e:
        print(f"Error saving data to database: {e}")
        return False

# Function to check internet connectivity
def is_connected():
    try:
        requests.get('http://www.google.com', timeout=5)
        return True
    except requests.ConnectionError:
        return False

# Function to upload unpublished data to an external service (e.g., Supabase)
def upload_unpublished_data():
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        
        # Fetch and upload unpublished sensor data
        cursor.execute("SELECT * FROM fo_sensor_data WHERE published = FALSE")
        data = cursor.fetchall()
        if data:
            formatted_data = []
            ids = []
            for row in data:
                ids.append(row[0])  # Assuming id is the first column
                formatted_data.append({
                    'timestamp': datetime_to_str(row[1]),
                    'cstr_ph': row[2],
                    'feed_ec': row[6],
                    'cstr_orp': row[3],
                    'ds_ec': row[14],
                    'cstr_temp': row[4],
                    'cstr_level': row[5],
                    'feed_level': row[7],
                    'feed_tds': row[8],
                    'feed_temp': row[9],
                    'ds_tds': row[15],
                    'ds_level': row[16],
                    'vol_to_ds': row[10],
                    'com_vol_fs': row[11],
                    'flux': row[12],
                    'increase_in_fs': row[13]
                })
            response = upload_data_to_external_service(formatted_data)
            if response and response.data:
                update_published_status(ids)
                print("Sensor data uploaded and marked as published successfully.")
            else:
                print("Error uploading sensor data to external service")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error uploading unpublished data: {e}")

# Function to upload sensor data to an external service (e.g., Supabase)
def upload_data_to_external_service(data):
    try:
        response = supabase.table('fo_sensor_data').insert(data).execute()
        return response
    except Exception as e:
        print(f"Error uploading data to external service: {e}")
        return None

# Function to update published status in the PostgreSQL database
def update_published_status(ids):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        ids_tuple = tuple(ids)
        update_query = "UPDATE fo_sensor_data SET published = TRUE WHERE id IN %s"
        cursor.execute(update_query, (ids_tuple,))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error updating published status: {e}")

# Main loop to handle data processing
def main_loop():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    while True:
        time.sleep(30)  # Check every minute

        # Save data to local database
        success = save_to_database(sensor_data)
        if success:
            sensor_data['published'] = False

        # Check for internet connection and upload unpublished data
        if is_connected():
            upload_unpublished_data()

if __name__ == '__main__':
    main_loop()
