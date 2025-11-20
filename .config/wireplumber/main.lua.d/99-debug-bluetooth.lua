-- Enable debug logging for Bluetooth monitoring
log = Log.open_topic ("s-monitors")
log:set_level (5, true)

-- Additional logging for bluez5 API
bluez_log = Log.open_topic ("api.bluez5")
bluez_log:set_level (5, true)
