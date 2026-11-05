# PWA 0.5.141

- Prevents stale LAN readbacks from reversing an optimistic Tuya switch state before the Gateway confirms the command.
- Updates Home favorite controls in place instead of replacing the card DOM; stabilizes metric card heights to prevent vertical page jumps.
- Preserves the Home scroll position by avoiding scroll restoration during live refreshes.
