import passlib
import bcrypt
import sys

print(f"Python executable: {sys.executable}")
print(f"passlib version: {passlib.__version__}")
try:
    #This is the problematic attribute
    print(f"bcrypt version via __about__: {bcrypt.__about__.__version__}")
except AttributeError as e:
    print(f"bcrypt version check failed: {e}")

try:
    # A different way to check version if available
    print(f"bcrypt version via __version__: {bcrypt.__version__}")
except AttributeError:
    print("bcrypt has no __version__ attribute either.")

print(f"passlib path: {passlib.__file__}")
print(f"bcrypt path: {bcrypt.__file__}")
