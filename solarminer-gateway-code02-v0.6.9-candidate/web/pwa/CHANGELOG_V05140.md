# PWA 0.5.140

- Sends switch orders with an immediate pending state and performs a one-round LAN readback for prompt confirmation.
- Uses a shared, debounced LAN readback after Tuya level and setting commands, with send, readback, and total timings shown in device details.
- Applies Shelly switch and light orders without waiting for a full inventory refresh; keeps the control responsive and reports command timing.
- Updates Home live values and device cards in place, skips unchanged card content, and preserves the current scroll position instead of rebuilding the page every poll.