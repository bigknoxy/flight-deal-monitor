import time

t0 = time.time()
import app.database  # noqa: F401

print("IMPORT_OK", round(time.time() - t0, 2))
