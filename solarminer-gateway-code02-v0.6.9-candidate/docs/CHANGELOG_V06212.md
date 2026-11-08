# Gateway 0.6.212

- Reduce periodic Deye Modbus sampling from every 3 seconds to every 15 seconds; persist at the same interval.
- Serialize Deye reads across the periodic sampler and manual read endpoint. Overlapping manual reads are rejected as busy; periodic samples skip instead of opening another Modbus conversation.
- Keep each Modbus request timeout bounded at 2 seconds so a failed read cannot hold Gateway workers for an extended period.
- Retain the asynchronous, I/O-free health endpoint from 0.6.211 and the watchdog action pause from 0.6.210.
