SEQUENCE = {
    "default_velocities": [20000, 20000, 20000, 20000, 20000, 20000],
    "default_currents": [1000, 1000, 1000, 1000, 1000, 1000],
    "default_interval": 0.8,
    "steps": [
        {"positions": [9000, 0, 0, 0, 0, 0]},
        {"positions": [9000, 0, 10000, 10000, 10000, 10000]},
        {"positions": [9000, 10000, 10000, 10000, 10000, 10000], "interval": 4.0},
        {"positions": [9000, 0, 10000, 10000, 10000, 10000]},
        {"positions": [9000, 0, 0, 0, 0, 0], "interval": 1.0},
    ],
}
