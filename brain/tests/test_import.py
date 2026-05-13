
print("Starting import...")
try:
    from brain.runtime import BrainRuntime
    print("Import success")
except Exception as e:
    print(f"Import failed: {e}")
except SystemExit:
    print("SystemExit during import")
