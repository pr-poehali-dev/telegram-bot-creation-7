CREATE TABLE IF NOT EXISTS sender_orders (
    id SERIAL PRIMARY KEY,
    pickup_address TEXT NOT NULL,
    pickup_comments TEXT,
    warehouse TEXT NOT NULL,
    delivery_date DATE,
    cargo_type VARCHAR(10) NOT NULL CHECK (cargo_type IN ('pallet', 'box')),
    cargo_quantity INTEGER,
    sender_name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NOT NULL,
    photo_url TEXT,
    label_size VARCHAR(10) CHECK (label_size IN ('120x75', '58x40')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS carrier_orders (
    id SERIAL PRIMARY KEY,
    car_brand VARCHAR(100) NOT NULL,
    car_model VARCHAR(100),
    license_plate VARCHAR(50) NOT NULL,
    capacity_type VARCHAR(10) NOT NULL CHECK (capacity_type IN ('pallet', 'box')),
    capacity_quantity INTEGER,
    warehouse TEXT,
    driver_name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NOT NULL,
    license_number VARCHAR(50),
    photo_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sender_created_at ON sender_orders(created_at DESC);
CREATE INDEX idx_carrier_created_at ON carrier_orders(created_at DESC);