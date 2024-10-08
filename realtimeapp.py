from customtkinter import *
from PIL import Image
import tkinter as tk
from tkinter import Menu, filedialog, messagebox
import psycopg2
import pandas as pd
import matplotlib.pyplot as plt
from tkcalendar import DateEntry
from datetime import datetime, timedelta
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import paho.mqtt.client as mqtt
import os

# MQTT Configuration
MQTT_BROKER = "192.168.18.28"
MQTT_PORT = 1883
MQTT_TOPICS = {
    "cstr-ph": "cstr_ph",
    "cstr-orp": "cstr_orp",
    "cstr-temp": "cstr_temp",
    "cstr-level": "cstr_level",
    "feed-ec": "feed_ec",
    "feed-temp": "feed_temp",
    "feed-level": "feed_level",
    "feed-tds": "feed_tds",
    "ds-tds": "ds_tds",
    "ds-ec": "ds_ec",
    "ds-level": "ds_level",
    "weight": "weight",
    # "flux": "flux"  # Flux data will be fetched from the database
}

# Initialize MQTT values storage
mqtt_values = {topic: None for topic in MQTT_TOPICS.keys()}

# Add global variables for settings
set_cstr_temp_value = None
set_ec_value = None
set_feed_level_value = None

# MQTT callback functions
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    for topic in MQTT_TOPICS.keys():
        client.subscribe(topic)

def on_message(client, userdata, msg):
    topic = msg.topic
    value = msg.payload.decode()
    mqtt_values[topic] = value
    update_ui_values()

# Initialize MQTT client and connect
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# Database configuration
DB_NAME = "sensordata"
DB_USER = "postgres"
DB_PASSWORD = "400220"
DB_HOST = "localhost"
DB_PORT = "5432"

# Function to fetch flux data from the database
def fetch_flux_data():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute("SELECT flux FROM fo_sensor_data ORDER BY timestamp DESC LIMIT 1")
        flux_value = cursor.fetchone()
        conn.close()

        if flux_value:
            return flux_value[0]
        else:
            return None
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while fetching flux data: {e}")
        return None

# Function to fetch data and display time series graph
def fetch_and_display_timeseries(param, from_date, to_date, canvas, figure, parent_window):
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
        )
        query = f"SELECT timestamp, {param} FROM fo_sensor_data WHERE timestamp BETWEEN '{from_date}' AND '{to_date}'"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            messagebox.showinfo("No Data", "No data found for the selected range.")
            parent_window.grab_release()
            parent_window.destroy()
            return

        # Plotting the data
        ax = figure.add_subplot(111)
        ax.clear()
        ax.plot(pd.to_datetime(df['timestamp']), df[param], marker='o', linestyle='-')
        ax.set_title(f'Time Series Data for {param}')
        ax.set_xlabel('Timestamp')
        ax.set_ylabel(param)
        ax.grid(True)
        canvas.draw()

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")
        parent_window.grab_release()
        parent_window.destroy()

# Function to save the graph as an image
def save_graph_as_image(figure, parent_window):
    file_path = filedialog.asksaveasfilename(initialdir="/home/resurgencefo/pictures", defaultextension=".png", filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg")])
    if file_path:
        figure.savefig(file_path)
        messagebox.showinfo("Success", "Image has been saved successfully.")
        parent_window.grab_release()
        parent_window.destroy()

# Function to open the time series window
def open_timeseries_window(param):
    timeseries_window = CTkToplevel()
    timeseries_window.title(f"Time Series Graph for {param}")
    timeseries_window.geometry("800x600")

    # Ensure the window is visible before grabbing
    timeseries_window.update_idletasks()
    timeseries_window.after(100, lambda: timeseries_window.grab_set())

    input_frame = CTkFrame(timeseries_window)
    input_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

    row1_frame = CTkFrame(input_frame)
    row1_frame.pack(side=tk.TOP, fill=tk.X)

    from_date_label = CTkLabel(row1_frame, text="From Date:")
    from_date_label.pack(side=tk.LEFT, padx=5)
    from_date_input = DateEntry(row1_frame, date_pattern='yyyy-mm-dd')
    from_date_input.pack(side=tk.LEFT, padx=5)

    from_time_label = CTkLabel(row1_frame, text="From Time (HH:MM):")
    from_time_label.pack(side=tk.LEFT, padx=5)
    from_time_input = CTkEntry(row1_frame)
    from_time_input.pack(side=tk.LEFT, padx=5)

    row2_frame = CTkFrame(input_frame)
    row2_frame.pack(side=tk.TOP, fill=tk.X, pady=(10, 0))

    to_date_label = CTkLabel(row2_frame, text="To Date:")
    to_date_label.pack(side=tk.LEFT, padx=5)
    to_date_input = DateEntry(row2_frame, date_pattern='yyyy-mm-dd')
    to_date_input.pack(side=tk.LEFT, padx=5)

    to_time_label = CTkLabel(row2_frame, text="To Time (HH:MM):")
    to_time_label.pack(side=tk.LEFT, padx=5)
    to_time_input = CTkEntry(row2_frame)
    to_time_input.pack(side=tk.LEFT, padx=5)

    fetch_button = CTkButton(row2_frame, text="Show Graph", command=lambda: fetch_and_display())
    fetch_button.pack(side=tk.LEFT, padx=5)

    save_button = CTkButton(row2_frame, text="Save Image", command=lambda: save_graph_as_image(figure, timeseries_window))
    save_button.pack(side=tk.LEFT, padx=5)

    figure = plt.Figure()
    canvas = FigureCanvasTkAgg(figure, master=timeseries_window)
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

    def fetch_and_display():
        from_date_str = from_date_input.get_date().strftime('%Y-%m-%d')
        from_time_str = from_time_input.get()
        to_date_str = to_date_input.get_date().strftime('%Y-%m-%d')
        to_time_str = to_time_input.get()

        from_datetime = f"{from_date_str} {from_time_str}:00"
        to_datetime = f"{to_date_str} {to_time_str}:00"

        fetch_and_display_timeseries(param, from_datetime, to_datetime, canvas, figure, timeseries_window)

    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    fetch_and_display_timeseries(param, one_hour_ago.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S'), canvas, figure, timeseries_window)

# Example function to bind to a parameter frame click event
def on_param_frame_click(param):
    open_timeseries_window(param)

# Function to save settings to the database
def save_settings(set_cstr_temp_input, set_ec_input, set_feed_level_input, settings_window):
    global set_cstr_temp_value, set_ec_value, set_feed_level_value
    try:
        # Convert input values to float
        set_cstr_temp = float(set_cstr_temp_input.get())
        set_ec = float(set_ec_input.get())
        set_feed_level = float(set_feed_level_input.get())

        # Save settings to the database
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
        )
        now = datetime.now()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO fo_setting (timestamp, set_cstr_temp, set_ec, published, set_feed_level) VALUES (%s, %s, %s, %s, %s)",
            (now, set_cstr_temp, set_ec, False, set_feed_level)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Update the global variables
        set_cstr_temp_value = set_cstr_temp
        set_ec_value = set_ec
        set_feed_level_value = set_feed_level

        messagebox.showinfo("Success", "Settings have been saved successfully.")
        settings_window.grab_release()
        settings_window.destroy()
    except ValueError:
        messagebox.showerror("Invalid Input", "All fields must be numeric values.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")
        settings_window.grab_release()
        settings_window.destroy()

def open_settings():
    global set_cstr_temp_value, set_ec_value, set_feed_level_value
    settings_window = CTkToplevel()
    settings_window.title("Settings")
    settings_window.geometry("600x400")

    # Ensure the window is visible before grabbing
    settings_window.update_idletasks()
    settings_window.after(100, lambda: settings_window.grab_set())

    set_cstr_temp_label = CTkLabel(settings_window, text="Set CSTR Temp:", font=("Helvetica", 18))
    set_cstr_temp_label.pack(pady=5)
    set_cstr_temp_input = CTkEntry(settings_window, font=("Helvetica", 18))
    set_cstr_temp_input.pack(pady=5)

    set_ec_label = CTkLabel(settings_window, text="Set EC:", font=("Helvetica", 18))
    set_ec_label.pack(pady=5)
    set_ec_input = CTkEntry(settings_window, font=("Helvetica", 18))
    set_ec_input.pack(pady=5)

    set_feed_level_label = CTkLabel(settings_window, text="Set Feed Level:", font=("Helvetica", 18))
    set_feed_level_label.pack(pady=5)
    set_feed_level_input = CTkEntry(settings_window, font=("Helvetica", 18))
    set_feed_level_input.pack(pady=5)

    save_button = CTkButton(settings_window, text="Save Settings", command=lambda: save_settings(set_cstr_temp_input, set_ec_input, set_feed_level_input, settings_window), font=("Helvetica", 18))
    save_button.pack(pady=20)

    # Fetch the latest settings from the database
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute("SELECT set_cstr_temp, set_ec, set_feed_level FROM fo_setting ORDER BY timestamp DESC LIMIT 1")
        latest_settings = cursor.fetchone()
        conn.close()

        if latest_settings:
            set_cstr_temp_input.insert(0, str(latest_settings[0]))
            set_ec_input.insert(0, str(latest_settings[1]))
            set_feed_level_input.insert(0, str(latest_settings[2]))


            # Update the global variables
            set_cstr_temp_value = latest_settings[0]
            set_ec_value = latest_settings[1]
            set_feed_level_value = latest_settings[2]

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while fetching settings: {e}")
        settings_window.grab_release()
        settings_window.destroy()


# Function to fetch the latest settings at startup
def fetch_latest_settings():
    global set_cstr_temp_value, set_ec_value, set_feed_level_value
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute("SELECT set_cstr_temp, set_ec, set_feed_level FROM fo_setting ORDER BY timestamp DESC LIMIT 1")
        latest_settings = cursor.fetchone()
        conn.close()

        if latest_settings:
            set_cstr_temp_value = latest_settings[0]
            set_ec_value = latest_settings[1]
            set_feed_level_value = latest_settings[2]
        else:
            set_cstr_temp_value = None
            set_ec_value = None
            set_feed_level_value = None

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while fetching settings: {e}")

# Function to publish settings to MQTT topics every 1 minute
def publish_settings():
    mqtt_client.publish("set-temp", str(set_cstr_temp_value))
    mqtt_client.publish("set-ec", str(set_ec_value))
    mqtt_client.publish("set-feed-level", str(set_feed_level_value))
    app.after(60000, publish_settings)  # Schedule to run every 1 minute

# Function to download data as CSV
def download_data(from_date_input, to_date_input, download_window):
    from_date = from_date_input.get_date().strftime('%Y-%m-%d %H:%M:%S')
    to_date = to_date_input.get_date().strftime('%Y-%m-%d %H:%M:%S')

    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
        )
        query = f"SELECT * FROM fo_sensor_data WHERE timestamp BETWEEN '{from_date}' AND '{to_date}'"
        df = pd.read_sql_query(query, conn)
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")], initialdir="/home/resurgencefo/pictures")
        if file_path:
            df.to_csv(file_path, index=False)
            conn.close()
            messagebox.showinfo("Success", "Data has been downloaded successfully.")
            download_window.grab_release()
            download_window.destroy()
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")
        download_window.grab_release()
        download_window.destroy()

# Function to open the download window
def open_download():
    download_window = CTkToplevel()
    download_window.title("Download Data")
    download_window.geometry("600x400")

    # Ensure the window is visible before grabbing
    download_window.update_idletasks()
    download_window.after(100, lambda: download_window.grab_set())

    from_date_label = CTkLabel(download_window, text="From Date:", font=("Helvetica", 18))
    from_date_label.pack(pady=10)
    from_date_input = DateEntry(download_window, date_pattern='yyyy-mm-dd', font=("Helvetica", 18))
    from_date_input.pack(pady=10)

    to_date_label = CTkLabel(download_window, text="To Date:", font=("Helvetica", 18))
    to_date_label.pack(pady=10)
    to_date_input = DateEntry(download_window, date_pattern='yyyy-mm-dd', font=("Helvetica", 18))
    to_date_input.pack(pady=10)

    download_button = CTkButton(download_window, text="Download", command=lambda: download_data(from_date_input, to_date_input, download_window), font=("Helvetica", 18))
    download_button.pack(pady=20)

app = CTk()
app.title("Aquameter Forward Osmosis")
app.geometry('1024x600')

# Create a menu
menu_bar = Menu(app)
app.config(menu=menu_bar)
menu_bar.add_command(label="Settings", command=open_settings)
menu_bar.add_command(label="Download", command=open_download)

# Load logos
left_logo_image = Image.open("/home/resurgencefo/foscripts/nust-logo.png")
right_logo_image = Image.open("/home/resurgencefo/foscripts/resurgence_logo.png")

left_logo_image = left_logo_image.resize((100, 100), Image.LANCZOS)
right_logo_image = right_logo_image.resize((480, 75), Image.LANCZOS)

left_logo_ctk_image = CTkImage(light_image=left_logo_image, dark_image=left_logo_image, size=(80, 80))
right_logo_ctk_image = CTkImage(light_image=right_logo_image, dark_image=right_logo_image, size=(250, 50))

title_frame = CTkFrame(master=app, fg_color="transparent")
title_frame.grid(row=0, column=0, columnspan=3, sticky="n")

left_logo_label = CTkLabel(master=title_frame, image=left_logo_ctk_image, text="")
left_logo_label.grid(row=0, column=0, padx=20, sticky="w")

right_logo_label = CTkLabel(master=title_frame, image=right_logo_ctk_image, text="")
right_logo_label.grid(row=0, column=2, padx=20, sticky="e")

title_label = CTkLabel(master=title_frame, text="Forward Osmosis", font=("Times New Roman", 44, 'bold'))
title_label.grid(row=0, column=1, pady=10)

sections = ["Anaerobic CSTR", "Feed Tank", "DS Tank"]

anaerobic_cstr_params = [
    ("PH", "cstr-ph", "cstr_ph", " /14"),
    ("ORP", "cstr-orp", "cstr_orp", " mV"),
    ("Temp", "cstr-temp", "cstr_temp", " °C"),
    ("Level", "cstr-level", "cstr_level", " Liters"),
    ("DS Weight", "weight", "weight", " g"),
    ("Flux", "flux", "flux", " LMH")  # Flux data fetched from database
]

feed_tank_params = [
    ("EC", "feed-ec", "feed_ec", " mS/cm"),
    ("TDS", "feed-tds", "feed_tds", " PPM"),
    ("Level", "feed-level", "feed_level", " mL"),
]

ds_params = [
    ("EC", "ds-ec", "ds_ec", " mS/cm"),
    ("TDS", "ds-tds", "ds_tds", " PPM"),
    ("Level", "ds-level", "ds_level", " mL"),
]

parameters = [anaerobic_cstr_params, feed_tank_params, ds_params]

value_labels = {}

for i, section in enumerate(sections):
    section_frame = CTkFrame(master=app, fg_color="transparent")
    section_frame.grid(row=1, column=i, padx=20, pady=20, sticky="nsew")

    section_label = CTkLabel(master=section_frame, text=section, font=("Times New Roman", 24, 'bold'), fg_color="#ffede0", corner_radius=15)
    section_label.grid(row=0, column=0, columnspan=2, pady=10)

    if section == "Anaerobic CSTR":
        for j, (param, topic, col, unit) in enumerate(parameters[i]):
            if topic == "flux":
                value = fetch_flux_data()  # Fetch flux data from the database
            else:
                value = mqtt_values[topic]
            param_frame = CTkFrame(master=section_frame, height=100, width=200, fg_color="#cfeaf7")
            param_frame.grid(row=(j // 2) + 1, column=j % 2, pady=10, padx=20, sticky="nsew")

            value_label = CTkLabel(master=param_frame, text=f"{value}{unit}", font=("Times New Roman", 32, 'bold'))
            value_label.place(relx=0.5, rely=0.3, anchor="center")
            value_labels[topic] = value_label
            border_line = CTkFrame(master=param_frame, height=2, width=200, fg_color="black")
            border_line.place(relx=0.5, rely=0.6, anchor="center")
            param_label = CTkLabel(master=param_frame, text=f"{param}", font=("Times New Roman", 20, 'bold'))
            param_label.place(relx=0.5, rely=0.65, anchor="n")

            param_frame.bind("<Button-1>", lambda e, param=col: on_param_frame_click(param))

    else:
        for j, (param, topic, col, unit) in enumerate(parameters[i]):
            value = mqtt_values[topic]
            param_frame = CTkFrame(master=section_frame, height=100, width=200, fg_color="#cfeaf7")
            param_frame.grid(row=j + 1, column=0, pady=10, padx=20, sticky="nsew")

            value_label = CTkLabel(master=param_frame, text=f"{value}{unit}", font=("Times New Roman", 32, 'bold'))
            value_label.place(relx=0.5, rely=0.3, anchor="center")
            value_labels[topic] = value_label
            border_line = CTkFrame(master=param_frame, height=2, width=200, fg_color="black")
            border_line.place(relx=0.5, rely=0.6, anchor="center")
            param_label = CTkLabel(master=param_frame, text=f"{param}", font=("Times New Roman", 20, 'bold'))
            param_label.place(relx=0.5, rely=0.65, anchor="n")

            param_frame.bind("<Button-1>", lambda e, param=col: on_param_frame_click(param))

footer_frame = CTkFrame(master=app, fg_color="transparent")
footer_frame.grid(row=2, column=0, columnspan=3, pady=5)
company_logo_image = Image.open("/home/resurgencefo/foscripts/company-logo.png")
company_logo_image = company_logo_image.resize((100, 50), Image.LANCZOS)
company_logo_ctk_image = CTkImage(light_image=company_logo_image, dark_image=company_logo_image, size=(100, 20))
company_logo_label = CTkLabel(master=footer_frame, image=company_logo_ctk_image, text="")
company_logo_label.grid(row=0, column=1, padx=20, sticky="e")

copyright_label = CTkLabel(master=footer_frame, text="All rights reserved © 2024 Pentaprism Technologies.", font=("Times New Roman", 12))
copyright_label.grid(row=0, column=0, pady=10)

for i in range(3):
    app.grid_columnconfigure(i, weight=1)
app.grid_rowconfigure(1, weight=1)

def update_ui_values():
    for i, section in enumerate(sections):
        if section == "Anaerobic CSTR":
            for j, (param, topic, col, unit) in enumerate(parameters[i]):
                if topic == "flux":
                    # Fetch flux data from the database
                    value = fetch_flux_data()
                else:
                    value = mqtt_values[topic]
                value_label = value_labels[topic]
                value_label.configure(text=f"{value}{unit}")
        else:
            for j, (param, topic, col, unit) in enumerate(parameters[i]):
                value = mqtt_values[topic]
                value_label = value_labels[topic]
                value_label.configure(text=f"{value}{unit}")

def periodically_update_ui():
    update_ui_values()
    app.after(1000, periodically_update_ui)

# Fetch the latest settings at startup and start publishing
fetch_latest_settings()
publish_settings()
app.after(1000, periodically_update_ui)
app.mainloop()
