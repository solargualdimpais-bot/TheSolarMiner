# Gateway 0.6.235

- Fix interrupted rollback recovery when the Gateway service is already stopped: queue a non-blocking service start after the recovery oneshot, and keep retrying/health-checking until the previous release is healthy.
- Gate online updates on both the verified local API and the local Nginx proxy, so a 502 cannot be accepted as a healthy release.
- Extend the USB repair validation to check both the backend API and Nginx proxy before declaring the repair successful.
