SELECT
    customer_name,
    total_orders,
    total_spent,
    RANK() OVER (ORDER BY total_spent DESC) AS customer_rank
FROM (
    SELECT
        c.first_name || ' ' || c.last_name AS customer_name,
        COUNT(DISTINCT o.order_id) AS total_orders,
        SUM(ol.quantity * ol.unit_price) AS total_spent
    FROM shopey.customers c
    JOIN shopey.orders o
        ON c.customer_id = o.customer_id
    JOIN shopey.order_lines ol
        ON o.order_id = ol.order_id
    GROUP BY
        c.customer_id,
        c.first_name,
        c.last_name
) customer_summary
ORDER BY customer_rank ASC;



-- #create tables and insert sample data in tables
create schema shopey;

-- Customers 
CREATE TABLE shopey.customers ( 
  customer_id   INT IDENTITY(1,1) PRIMARY KEY, 
  first_name    VARCHAR(100) NOT NULL, 
  last_name     VARCHAR(100) NOT NULL, 
  email         VARCHAR(255) UNIQUE NOT NULL, 
  phone         VARCHAR(20), 
  created_at    DateTime DEFAULT GETDATE()
); 
  -- Categories 
CREATE TABLE shopey.categories ( 
  category_id   INT IDENTITY(1,1) PRIMARY KEY, 
  category_name VARCHAR(100) NOT NULL, 
  description   TEXT 
); 

-- Vendors 
CREATE TABLE shopey.vendors ( 
  vendor_id     INT IDENTITY(1,1) PRIMARY KEY, 
  vendor_name   VARCHAR(150) NOT NULL, 
  contact_email VARCHAR(255) 
); 
  -- Products 
CREATE TABLE shopey.products ( 
  product_id    INT IDENTITY(1,1) PRIMARY KEY, 
  product_name  VARCHAR(200) NOT NULL, 
  category_id   INT REFERENCES shopey.categories(category_id), 
  vendor_id     INT REFERENCES shopey.vendors(vendor_id), 
  unit_price    NUMERIC(10,2) NOT NULL CHECK (unit_price >= 0), 
  stock_qty     INT DEFAULT 0 
);

-- Orders 
CREATE TABLE shopey.orders ( 
order_id      
INT IDENTITY(1,1) PRIMARY KEY, 
customer_id   INT NOT NULL REFERENCES shopey.customers(customer_id), 
order_date     DateTime DEFAULT GETDATE(), 
status        
VARCHAR(20) CHECK (status IN ('Pending','Confirmed','Shipped','Delivered','Cancelled')) 
DEFAULT 'Pending' 
); 

-- Order Lines 
CREATE TABLE shopey.order_lines ( 
line_id       
INT IDENTITY(1,1) PRIMARY KEY, 
order_id      
INT NOT NULL REFERENCES shopey.orders(order_id), 
product_id    INT NOT NULL REFERENCES shopey.products(product_id), 
quantity      
INT NOT NULL CHECK (quantity > 0), 
unit_price    NUMERIC(10,2) NOT NULL 
); -- Payments 
CREATE TABLE shopey.payments ( 
payment_id    INT IDENTITY(1,1) PRIMARY KEY, 
order_id      
INT UNIQUE NOT NULL REFERENCES shopey.orders(order_id), 
payment_date  DATETIME, 
method        
VARCHAR(50) CHECK (method IN ('Card','PayPal','Bank Transfer','Wallet')), 
amount NUMERIC(10,2) NOT NULL,      
status VARCHAR(20) CHECK (status IN ('Pending','Paid','Failed','Refunded')) DEFAULT 'Pending'   
);
 

INSERT INTO shopey.customers (first_name, last_name, email, phone)
VALUES
('Alice', 'Smith', 'alice@example.com', '9876543210'),
('Bob', 'Johnson', 'bob@example.com', '9876543211'),
('Carol', 'White', 'carol@example.com', '9876543212');

INSERT INTO shopey.categories (category_name, description)
VALUES
('Electronics', 'Electronic products'),
('Books', 'Books and magazines');

INSERT INTO shopey.vendors (vendor_name, contact_email)
VALUES
('TechVendor', 'tech@vendor.com'),
('BookVendor', 'books@vendor.com');

INSERT INTO shopey.products
(product_name, category_id, vendor_id, unit_price, stock_qty)
VALUES
('Laptop', 1, 1, 50000.00, 10),
('Mouse', 1, 1, 1000.00, 50),
('SQL Book', 2, 2, 500.00, 100);

INSERT INTO shopey.orders (customer_id, status)
VALUES
(1, 'Delivered'),
(1, 'Delivered'),
(2, 'Delivered'),
(3, 'Delivered');

INSERT INTO shopey.order_lines
(order_id, product_id, quantity, unit_price)
VALUES
(1, 1, 1, 50000.00),
(1, 2, 2, 1000.00),
(2, 3, 5, 500.00),
(3, 1, 1, 50000.00),
(4, 2, 10, 1000.00);
