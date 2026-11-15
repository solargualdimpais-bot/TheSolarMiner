from solarminer_gateway.smart_device_engine import SmartDeviceScheduler


def test_each_device_uses_its_own_latest_latency_and_waits_twice_that_after_response():
    scheduler = SmartDeviceScheduler()
    scheduler.reconcile([("tuya", "fast"), ("shelly", "slow")], 10.0)
    fast, slow = scheduler.due(10.0, 2)
    scheduler.complete(fast, 10.2, 0.2, True)
    scheduler.complete(slow, 10.8, 0.8, True)

    assert fast.next_poll_monotonic == 10.6
    assert slow.next_poll_monotonic == 12.4
    assert scheduler.due(10.59, 2) == []
    assert scheduler.due(10.6, 2) == [fast]
    scheduler.complete(fast, 10.8, 0.3, True)
    assert fast.next_poll_monotonic == 11.4
    assert slow.next_poll_monotonic == 12.4


def test_offline_deadline_is_five_times_device_latency_and_recovers_on_response():
    scheduler = SmartDeviceScheduler()
    scheduler.reconcile([("tuya", "plug")], 0.0)
    device = scheduler.due(0.0, 1)[0]
    scheduler.complete(device, 1.0, 0.4, True)

    assert device.is_online(2.999)
    assert device.is_online(3.0)
    assert not device.is_online(3.001)
    assert not scheduler.needs_cloud_check(device, 2.999)
    assert scheduler.needs_cloud_check(device, 3.001)
    assert not scheduler.needs_cloud_check(device, 3.1)
    scheduler.complete_cloud_check(device)
    assert not scheduler.needs_cloud_check(device, 30.0)

    device.next_poll_monotonic = 30.0
    assert scheduler.due(30.0, 1) == [device]
    scheduler.complete(device, 30.2, 0.4, True)
    assert device.is_online(30.2)
    assert device.last_success_monotonic == 30.2
    assert not scheduler.needs_cloud_check(device, 32.199)
    assert scheduler.needs_cloud_check(device, 32.201)


def test_never_responded_device_is_not_online_and_cloud_check_is_single_per_outage():
    scheduler = SmartDeviceScheduler()
    scheduler.reconcile([("tuya", "new-device")], 4.0)
    device = scheduler.devices[("tuya", "new-device")]
    assert not device.is_online(4.0)
    assert not scheduler.needs_cloud_check(device, 4.0)
    scheduler.due(4.0, 1)
    scheduler.complete(device, 4.1, 0.1, False)
    assert not device.is_online(4.1)
    assert not scheduler.needs_cloud_check(device, 4.1)
    assert not scheduler.needs_cloud_check(device, 6.599)
    assert scheduler.needs_cloud_check(device, 6.6)
    scheduler.complete_cloud_check(device)
    assert not scheduler.needs_cloud_check(device, 4.3)


def test_slow_device_wait_is_not_capped_below_two_times_its_latency():
    scheduler = SmartDeviceScheduler()
    scheduler.reconcile([("tuya", "slow")], 0.0)
    device = scheduler.due(0.0, 1)[0]
    scheduler.complete(device, 40.0, 40.0, True)
    assert device.next_poll_monotonic == 120.0
    assert not device.is_online(240.001)


def test_scheduler_only_keeps_tuya_and_shelly_and_removes_unconfigured_devices():
    scheduler = SmartDeviceScheduler()
    scheduler.reconcile([("tuya", "one"), ("shelly", "two"), ("deye", "three")], 5.0)
    assert set(scheduler.devices) == {("tuya", "one"), ("shelly", "two")}
    scheduler.reconcile([("shelly", "two")], 6.0)
    assert set(scheduler.devices) == {("shelly", "two")}
