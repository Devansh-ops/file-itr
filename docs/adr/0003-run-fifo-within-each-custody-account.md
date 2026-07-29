---
status: accepted
---

# Run FIFO within each custody account

Indian delivery-security evidence can span several demat accounts, while FIFO
identification is account-local. The engine therefore keeps a separate tax-lot
queue for every custody-account and ISIN pair. A linked own-account transfer
consumes source-account lots in FIFO order and recreates those exact lot pieces
in the destination with original acquisition dates, basis, FMV attributes, and
evidence lineage. It is never modeled as a disposal or a fresh acquisition.
Deductible acquisition/transfer expenses are carried in basis, deductible sale
expenses reduce proceeds, and STT remains separately disclosed and never enters
either deduction.
