# Gateway 0.6.207

- Keep the Shelly dimmer slider at the selected target; update the measured brightness indicator from LAN feedback independently.
- Send the final dimmer target one second after the user releases the slider, and retain the selected value while the command is pending.
- Improve Shelly dimmer indicators, slider alignment and the circular power control.
- Persist the Shelly room/floor label with its device name.
- Keep registered Shelly devices in the confirmed inventory during short LAN read failures.

Validation includes the complete PWA contract suite and the official Linux Gateway test and release pipeline. Physical Shelly command confirmation still requires the user's device.
