import pandas as pd

def main():
    input_csv = "input.csv"
    try:
        df = pd.read_csv(input_csv)
        df.columns = df.columns.str.strip()  # Remove any leading/trailing spaces in headers
        print("Columns detected:", df.columns.tolist())
        print(df)
    except Exception as e:
        print(f"Error reading {input_csv}: {e}")

if __name__ == "__main__":
    main()
