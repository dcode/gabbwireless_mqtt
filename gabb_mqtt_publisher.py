import json
import logging
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

import log
from gabb import GabbClient

# Configurable Variables from Environment
GABB_USERNAME = os.getenv("GABB_USERNAME", "default_username")
GABB_PASSWORD = os.getenv("GABB_PASSWORD", "default_password")

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt.example.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "mqtt_user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "mqtt_password")
MQTT_DISCOVERY_TOPIC = os.getenv("MQTT_DISCOVERY_TOPIC", "homeassistant")

DEVICE_MODEL = "Gabb Device"
DEVICE_MANUFACTURER = "Gabb Wireless"

# Calculate LOOP_DELAY based on environment variable value
LOOP_DELAY_SETTING = int(os.getenv("REFRESH_RATE", "1"))
# Default to 30 minutes if invalid
LOOP_DELAY = {1: 300, 2: 600, 3: 1800, 4: 3600}.get(LOOP_DELAY_SETTING, 1800)

PUBLISH_DELAY = 0.1  # Delay in seconds between publishing each topic

logger: logging.Logger

# Global MQTT client
mqtt_client = mqtt.Client(protocol=mqtt.MQTTv5)  # Use MQTT version 5


def on_connect(client, userdata, flags, rc, properties=None):
  logger.info("Connected to MQTT broker with result code %s", rc)


def on_disconnect(client, userdata, rc, properties=None):
  logger.info("Disconnected from MQTT broker.")


def on_message(client, userdata, message):
  logger.info(
    "Received message on topic %s: %s", message.topic, message.payload.decode()
  )


def setup_mqtt_client():
  """
  Setup and connect the MQTT client.
  """
  try:
    logger.info(
      "Setting up MQTT client credentials: %s",
      {"username": MQTT_USERNAME, "password": MQTT_PASSWORD},
    )
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message

    logger.info(
      "Attempting to connect to MQTT broker at %s:%s", MQTT_HOST, MQTT_PORT
    )
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    logger.info("Connected.")
  except Exception:
    logger.exception("Failed to connect to MQTT broker")
    raise


def ensure_mqtt_connection():
  """
  Ensure that the MQTT client is connected.
  """
  if not mqtt_client.is_connected():
    logger.info("MQTT client disconnected. Attempting to reconnect...")
    try:
      mqtt_client.reconnect()
      logger.info("Reconnected to MQTT broker.")
    except Exception:
      logger.exception("Failed to reconnect to MQTT broker")
      raise


def remove_key_recursive(obj, key_to_remove):
  """
  Recursively traverse a nested dictionary/list structure
  and remove all occurrences of `key_to_remove`.
  """
  if isinstance(obj, dict):
    obj.pop(key_to_remove, None)
    for value in obj.values():
      remove_key_recursive(value, key_to_remove)
  elif isinstance(obj, list):
    for item in obj:
      remove_key_recursive(item, key_to_remove)


def generate_mqtt_topics(map_data, root_topic="gabb_device"):
  """
  Generate MQTT topics for devices and their properties.
  """
  devices = map_data.get("data", {}).get("Devices", [])
  if not devices:
    logger.info("No devices found in the map data.")
    return {}

  mqtt_topics = {}
  for device in devices:
    device_id = device.get("id", "unknown")
    topic_prefix = f"{root_topic}/{device_id}"
    for key, value in device.items():
      topic = f"{topic_prefix}/{key}"
      mqtt_topics[topic] = value

    # Add a combined topic for location
    if "longitude" in device and "latitude" in device:
      location_payload = {
        "latitude": device["latitude"],
        "longitude": device["longitude"],
      }
      if "gpsDate" in device:
        location_payload["LastGPSUpdate"] = device["gpsDate"]
      mqtt_topics[f"{topic_prefix}/location"] = location_payload

    # Add a current UTC timestamp as a sensor
    current_utc_time = datetime.now(timezone.utc).isoformat()
    mqtt_topics[f"{topic_prefix}/last_updated"] = current_utc_time

  return mqtt_topics


def generate_homeassistant_discovery_messages(
  map_data, root_topic="gabb_device"
):
  """
  Generate Home Assistant MQTT discovery messages for devices.
  """
  devices = map_data.get("data", {}).get("Devices", [])
  if not devices:
    logging.info("No devices found in the map data.")
    return {}

  # Mapping of keys to device_class and unit_of_measurement
  key_to_device_class = {
    "batteryLevel": {"device_class": "battery", "unit_of_measurement": "%"},
    "longitude": {"device_class": None, "unit_of_measurement": "°"},
    "latitude": {"device_class": None, "unit_of_measurement": "°"},
    "gpsDate": {"device_class": "timestamp", "unit_of_measurement": None},
    "last_updated": {"device_class": "timestamp", "unit_of_measurement": None},
    "weight": {"device_class": "weight", "unit_of_measurement": "kg"},
  }

  discovery_messages = {}
  for device in devices:
    device_id = device.get("id", "unknown")
    device_name = f"Gabb Device {device_id}"
    base_topic = f"{MQTT_DISCOVERY_TOPIC}/sensor/{root_topic}_{device_id}"

    # Generate sensor discovery messages
    for key, _ in device.items():
      sensor_name = "".join(word.capitalize() for word in key.split("_"))
      sensor_topic = f"{base_topic}/{key}/config"
      device_class = key_to_device_class.get(key, {}).get("device_class")
      unit_of_measurement = key_to_device_class.get(key, {}).get(
        "unit_of_measurement"
      )
      discovery_payload = {
        "name": sensor_name,
        "state_topic": f"{root_topic}/{device_id}/{key}",
        "unique_id": f"{root_topic}_{device_id}_{key}",
        "device_class": device_class,
        "unit_of_measurement": unit_of_measurement,
        "device": {
          "identifiers": [f"{root_topic}_{device_id}"],
          "name": device_name,
          "model": DEVICE_MODEL,
          "manufacturer": DEVICE_MANUFACTURER,
        },
      }
      discovery_messages[sensor_topic] = discovery_payload

    # Add discovery message for the last updated sensor
    last_updated_topic = f"{base_topic}/last_updated/config"
    last_updated_payload = {
      "name": "Last Updated",
      "state_topic": f"{root_topic}/{device_id}/last_updated",
      "unique_id": f"{root_topic}_{device_id}_last_updated",
      "device_class": "timestamp",
      "device": {
        "identifiers": [f"{root_topic}_{device_id}"],
        "name": device_name,
        "model": DEVICE_MODEL,
        "manufacturer": DEVICE_MANUFACTURER,
      },
    }
    discovery_messages[last_updated_topic] = last_updated_payload

    # Generate device tracker discovery message
    if "longitude" in device and "latitude" in device:
      tracker_topic = (
        f"homeassistant/device_tracker/{root_topic}_{device_id}/config"
      )
      tracker_payload = {
        "name": device_name,
        "unique_id": f"{root_topic}_{device_id}_tracker",
        "json_attributes_topic": f"{root_topic}/{device_id}/location",
        "device": {
          "identifiers": [f"{root_topic}_{device_id}"],
          "name": device_name,
          "model": DEVICE_MODEL,
          "manufacturer": DEVICE_MANUFACTURER,
        },
      }
      discovery_messages[tracker_topic] = tracker_payload

  return discovery_messages


def publish_to_mqtt_broker(mqtt_topics, discovery_messages, delay=0.1):
  """
  Publish MQTT topics and Home Assistant discovery messages to the broker.
  """
  ensure_mqtt_connection()

  # Publish Home Assistant discovery messages
  for topic, payload in discovery_messages.items():
    try:
      mqtt_client.publish(topic, json.dumps(payload))
      logger.info("Published Home Assistant discovery message to %s", topic)
      logger.debug("Payload: %s", json.dumps(payload, indent=2))
      time.sleep(delay)
    except Exception:
      logger.exception(
        "Failed to publish Home Assistant discovery message to %s.", topic
      )

  # Publish regular MQTT topics
  for topic, value in mqtt_topics.items():
    try:
      mqtt_client.publish(
        topic,
        json.dumps(value) if isinstance(value, (dict, list)) else str(value),
      )
      logger.info("Published to %s", topic)
      logger.debug("Payload: %s", json.dumps(value, indent=2))
      time.sleep(delay)
    except Exception:
      logger.exception("Failed to publish %s.", topic)


def main():
  try:
    setup_mqtt_client()
  except Exception:
    logger.exception("Critical error during MQTT setup. Exiting...")
    return

  while True:
    logger.info("Starting new iteration...")
    try:
      # Initialize Gabb client
      try:
        client = GabbClient(GABB_USERNAME, GABB_PASSWORD)
      except Exception:
        logger.exception("Failed initializing the GabbClient", stack_info=True)
        logger.info("Waiting for %s seconds to try again...", LOOP_DELAY)
        time.sleep(LOOP_DELAY)
        continue
      logger.info("Initialized Gabb client.")

      # Fetch map data
      logger.info("Fetching map data...")
      map_response = client.get_map()
      try:
        map_data = map_response.json()
      except Exception:
        logger.exception("Failed to parse map data.")
        continue

      # Remove all "SafeZone" entries from the data
      remove_key_recursive(map_data, "SafeZones")

      # Generate MQTT topics
      logger.info("Processing map data...")
      mqtt_topics = generate_mqtt_topics(map_data)

      # Generate Home Assistant discovery messages for all properties
      logger.info("Generating Home Assistant discovery messages...")
      discovery_messages = generate_homeassistant_discovery_messages(map_data)

      if mqtt_topics or discovery_messages:
        # Publish to MQTT broker
        logger.info("Publishing topics to MQTT broker...")
        publish_to_mqtt_broker(
          mqtt_topics, discovery_messages, delay=PUBLISH_DELAY
        )
    except Exception:
      logger.exception("Error in iteration.", stack_info=True)

    logger.info("Iteration complete. Waiting for %s seconds...", LOOP_DELAY)
    time.sleep(LOOP_DELAY)


if __name__ == "__main__":
  try:
    log_level = os.getenv("LOG_LEVEL", "WARNING")
    if log_level.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
      logger = log.init_logging(log_level=log_level.upper())
    else:
      logger = log.init_logging(log_level="INFO")
    main()
  except KeyboardInterrupt:
    logger.error("Script interrupted by user.")
  except Exception:
    logger.exception("Unhandled exception.")
