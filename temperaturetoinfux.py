#!/usr/bin/python3

import codecs
from datetime import datetime, timezone

from influxdb_client import WritePrecision, InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

import time
import board
import adafruit_dht
import mh_z19
import datetime
import threading
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Initial the dht device, with data pin connected to:
dhtDevice = adafruit_dht.DHT22(board.D24)

while True:
    try:
        def th_reader():
            co2 = mh_z19.read_co2valueonly()
            # Print the values to the serial port
            temperature = dhtDevice.temperature
            humidity = dhtDevice.humidity

            if humidity is not None and temperature is not None:
                temp = '{0:0.1f}°C'.format(temperature)
                humid = '{0:0.1f}%'.format(humidity)
                return {
                        "temperature": temperature,
                        "humidity": humidity,
                        "co2": co2
                        }
            else:
                temp = None
                humid = None
                return {
                        "temperature": temp,
                        "humidity": humid,
                        "co2": co2
                        }
        def fan_control(data_to_control):
            temperature = data_to_control.get("temperature")
            humidity = data_to_control.get("humidity")

            if temperature > 26 or humidity > 60:
                print("fanon")
            if temperature < 20 or humidity < 40:
                print("fanoff")

        def write_to_influxdb(data_to_write):
            # You can generate an API token from the "API Tokens Tab" in the UI
            token = "influxtokenhere"
            org = "org"
            bucket = "sensordata"
            influx_url = "http://localhost:8086"
            with InfluxDBClient(url=influx_url, token=token, org=org) as client:
                write_api = client.write_api(write_options=SYNCHRONOUS)
                p = Point("sensordata01").tag("location", "rpi5").field("temperature", float(data_to_write.get("temperature"))).field("humidity", data_to_write.get("humidity")).field("co2", data_to_write.get("co2"))
                write_api.write(bucket, org, p)
                client.close()

            return True
        if __name__ == '__main__':
           th_data = th_reader()
           print(th_data)
        #    write_to_influxdb(data_to_write=th_data)
           t1 = threading.Thread(target=write_to_influxdb, kwargs={"data_to_write": th_data})
           t1.start()
    except RuntimeError as error:
        # Errors happen fairly often, DHT's are hard to read, just keep going
        print(error.args[0])
        time.sleep(5.0)
        continue
    except Exception as error:
        dhtDevice.exit()
        raise error

    time.sleep(5.0)
