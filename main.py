from quart import Quart, request, jsonify
import asyncio
from tapo import ApiClient, Color, EnergyDataInterval  # Import EnergyDataInterval
import os
import re
import colorsys


app = Quart(__name__)

# dot env

# Environment variables for TAPO credentials
TAPO_USERNAME = os.getenv("TAPO_USERNAME", "hamishapps@gmail.com")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD", "l1tHyr~s")
IP_ADDRESSES = {
    "kitchen_light": "192.168.68.60",
    "tv_light": "192.168.68.61",
    "living_room_plug": "192.168.68.64",
    "desk_light": "192.168.68.54",
    "bed_light": "192.168.68.51"
}

lights = {}

def rgb_to_hsv(r, g, b):
    return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)


@app.before_serving
async def initialize_lights():
    """Initialize connections to Tapo lights."""
    global lights
    client = ApiClient(TAPO_USERNAME, TAPO_PASSWORD)
    for name, ip in IP_ADDRESSES.items():
        try:
            if 'plug' in name:
                lights[name] = await client.p100(ip)
            else:
                lights[name] = await client.l530(ip)
            app.logger.info(f"Connected to {name} at {ip} successfully.")
        except Exception as e:
            app.logger.error(f"Failed to connect to {name} at {ip}: {e}")
            lights[name] = None

"""
Control lights
POST /control_lights
{
    "action": "on",  # on, off, toggle
    "lights": ["kitchen_light", "tv_light"]  # Optional, control specific lights
}

"""
@app.route('/control_lights', methods=['POST'])
async def control_lights():
    """Control specified or all lights to turn on, off, or toggle."""
    data = await request.get_json()
    action = data.get('action')
    light_names = data.get('lights', lights.keys())

    results = await asyncio.gather(*[
        control_light(lights[name], action) for name in light_names if lights[name]
    ], return_exceptions=True)

    response = {name: f"{action} successful" if not isinstance(res, Exception) else str(res)
                for name, res in zip(light_names, results)}
    return jsonify(response), 200

"""
Set properties for lights
POST /set_properties
{
    "brightness": 50,  # 0-100
    "color": [255, 0, 0],  # RGB color values
    "lights": ["kitchen_light", "tv_light"]  # Optional, set properties for specific lights
}
"""
@app.route('/set_properties', methods=['POST'])
async def set_properties():
    data = await request.get_json()
    brightness = data.get('brightness')
    rgb_color = data.get('color')  # Expecting color as RGB values (e.g., [255, 0, 0])
    light_names = data.get('lights', lights.keys())  # Set properties for specific or all lights

    if rgb_color:
        if all(0 <= value <= 255 for value in rgb_color):
            app.logger.info(f"RGB values: {rgb_color}")
            hue, saturation, value = rgb_to_hsv(*rgb_color)  # Convert RGB to HSV

            results = await asyncio.gather(*[
                set_light_properties(lights[name], brightness, hue, saturation, value, ip_address=IP_ADDRESSES[name], name=name) 
                for name in light_names if name in lights
            ])
            return jsonify({name: "Properties set successfully" for name in light_names}), 200
        else:
            app.logger.error(f"Invalid RGB values: {rgb_color}")
            return jsonify({"error": "Invalid RGB values. Each value should be between 0 and 255."}), 400
    else:
        # Handle brightness setting without color change
        results = await asyncio.gather(*[
            set_light_properties(lights[name], brightness, ip_address=IP_ADDRESSES[name], name=name) for name in light_names if name in lights
        ])
        return jsonify({name: "Brightness set successfully" for name in light_names}), 200
    
@app.route('/get_info', methods=['GET'])
async def get_info():
    """Retrieve information about specified or all connected lights."""
    light_names = request.args.getlist('lights')
    if not light_names:
        light_names = list(lights.keys())

    async def get_light_info(name):
        if name in lights:
            device_info = await get_device_info(lights[name])
            if isinstance(device_info, Exception):
                return name, {"error": str(device_info)}
            else:
                return name, {
                    'is_on': device_info.device_on,
                    'hue': getattr(device_info, 'hue', None),
                    'brightness': getattr(device_info, 'brightness', None)
                }
        return name, {"error": "Light not found"}

    results = await asyncio.gather(*[get_light_info(name) for name in light_names])
    results_dict = dict(results)

    return jsonify(results_dict), 200

async def set_light_properties(device, brightness=None, hue=None, saturation=None, value=None, ip_address=None, name=None):
    print(f"Device type for device at {ip_address}: {type(device)}") 
    print(dir(device)) 

    try:
        if brightness is not None:
            await device.on() if brightness > 0 else await device.off()
            await device.set_brightness(int(value * 100))  # Assuming 0-100 scale

        if hue is not None and saturation is not None:
            await device.set_hue_saturation(hue, saturation) 

        if name:
            return f"Properties set for device '{name}' at {ip_address}"
        else:
            return f"Properties set for device at {ip_address}"

    except Exception as e:
        return f"Error setting properties for device at {ip_address}: {e}"

 

async def control_light(device, action):
    """Control a light's state to on, off, or toggle based on the action."""
    if action == "on":
        await device.on()
    elif action == "off":
        await device.off()
    elif action == "toggle":
        device_info = await device.get_device_info()
        await device.off() if device_info.device_on else await device.on()
    return "action successful"

async def get_device_info(device):
    """Retrieve the current state information of a light."""
    return await device.get_device_info()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, use_reloader=False)