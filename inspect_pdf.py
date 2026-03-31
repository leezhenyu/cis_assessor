import fitz

doc = fitz.open("benchmark/CIS_Oracle_Linux_9_Benchmark_v2.0.0.pdf")
print(f"Total pages: {len(doc)}")

for i in range(15, 20):  # Let's inspect pages 15 to 20
    print(f"--- Page {i + 1} ---")
    print(doc[i].get_text())
