# MediBridge Hackathon Final MVP

Final build includes embedded video consultation, AI symptom-to-doctor matching, hospital partner portal, pandemic city/hospital hotspot intelligence, patient hotspot cards without Leaflet on the pandemic page, while the Patient Emergency map remains unchanged. Pharmacy supports an optional MediBridge sanitizer add-on (₹5) when medicine subtotal is ₹10 or more and provides a digital bill for every order.

Demo maps: patient Emergency map remains Leaflet/OpenStreetMap; admin has no map. Pandemic views use tables/cards only.

Demo credentials are in DEMO_CREDENTIALS_FINAL.txt.

## Diagnostics MVP

The patient portal now includes a Diagnostics section with seeded demo tests, booking for home sample collection or diagnostic-centre visits, preferred date/time, pricing, and a patient booking history. Diagnostic bookings are stored in the SQLite database in `diagnostic_tests` and `diagnostic_orders`.
