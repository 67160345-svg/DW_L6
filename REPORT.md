# ETL Lab Report

Student ID: 67160345
Name: นพรัตน์ โพธิ์สาวัง

## 1. Data Quality Problems Found
- **customers.csv**: มี customer_id ซ้ำ (C004, C009 ซ้ำกัน 1 ครั้ง), province เขียนไม่เป็นมาตรฐาน (เช่น "BKK", "chon buri", "ชลบุรี", "RAYONG", ตัวพิมพ์เล็ก/ใหญ่ปนกัน) และมีค่า province/email ที่หายไป (missing)
- **orders.csv**: order_id ซ้ำ 3 รายการ, order_date มีหลายรูปแบบปนกัน (YYYY/MM/DD, DD/MM/YYYY, YYYY-MM-DD, DD-Mon-YYYY) และมีค่าที่ parse ไม่ได้ ("not-a-date"), status เขียนตัวพิมพ์เล็ก/ใหญ่ปนกัน (เช่น "PAID" กับ "paid"), มี qty ติดลบ, unit_price ติดลบ, discount_pct เกิน 100, และมี customer_id/product_id ที่ไม่มีอยู่จริง (C999, P999)
- **products.json**: โครงสร้างเป็น nested JSON (category.name, pricing.price), price บางค่าเป็น string ที่มี comma คั่นหลักพัน (เช่น "1,299.00"), และ category บางรายการเป็น null

## 2. Cleaning / Transformation Rules
- Customers: ลบ customer_id ที่ซ้ำ (เก็บแถวแรก), map ค่าคำ province ที่หลากหลายให้เป็นค่ามาตรฐานเดียว (Chonburi/Bangkok/Rayong/Chanthaburi) ผ่าน PROVINCE_MAP ค่าที่ไม่รู้จักหรือว่างให้เป็น "Unknown", เติมค่า email ที่หายไปด้วย "unknown"
- Products: flatten JSON ด้วย pd.json_normalize แล้ว rename คอลัมน์ category.name → category, pricing.price → price, แปลง price เป็นตัวเลข (ตัด comma ออกก่อนแปลง), category ที่เป็น null ให้เป็น "Unknown"
- Orders: แปลง status เป็นตัวพิมพ์เล็กทั้งหมด, ลบ order_id ที่ซ้ำ (เก็บแถวแรก ส่วนที่เหลือ reject), parse order_date ด้วยหลายรูปแบบ (mixed format parser), reject แถวที่ qty<=0, unit_price<=0, discount_pct<0 หรือ >100, หรือ date parse ไม่ได้, กรองเก็บเฉพาะ status paid/completed, join กับ customers และ products แล้ว reject แถวที่ customer_id/product_id ไม่พบในตาราง master, คำนวณ gross_amount = qty*unit_price, discount_amount = gross_amount*discount_pct/100, sales_amount = gross_amount - discount_amount

## 3. Rejected Records
จำนวน: 83 รายการ (จากทั้งหมด 183 orders)

เหตุผลหลัก:
- status_not_paid_or_completed: 76 รายการ (สถานะเป็น pending หรือ cancelled)
- duplicate_order_id: 3 รายการ
- invalid_qty: 1 รายการ (qty ติดลบ)
- invalid_unit_price: 1 รายการ (unit_price ติดลบ)
- invalid_discount_pct: 1 รายการ (discount_pct = 150)
- invalid_date: 1 รายการ ("not-a-date")

## 4. ETL Validation
- Valid transformed rows: 100
- Warehouse rows: 100
- Duplicate order_id: 0
- Source total sales: 192,074.66
- Warehouse total sales: 192,074.66
- Validation status: PASS

## 5. Idempotency Test
จำนวน fact_sales หลัง run ครั้งที่ 1: 100

จำนวน fact_sales หลัง run ครั้งที่ 2: 100

อธิบายผล: จำนวนแถวใน fact_sales ไม่เพิ่มขึ้นหลังจาก run pipeline ซ้ำ เนื่องจากตาราง fact_sales กำหนด order_id เป็น PRIMARY KEY และการโหลดข้อมูลใช้คำสั่ง INSERT OR IGNORE ทำให้แถวที่มี order_id ซ้ำกับที่มีอยู่แล้วในฐานข้อมูลจะถูกข้ามไปโดยอัตโนมัติ ส่วน dim_customer และ dim_product ใช้ INSERT OR REPLACE (upsert) โดยยึด customer_id/product_id เป็น PRIMARY KEY เช่นกัน จึงมั่นใจได้ว่า pipeline นี้ทำงานแบบ idempotent
