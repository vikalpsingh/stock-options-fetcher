#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sort_by_premium.py
Filters, sorts, and saves OTM options to a formatted Excel with two styled sheets ("CALL" and "PUT").
"""

import pandas as pd
import sys
import os

MIN_PREMIUM = 4000

def autosize_columns(df, worksheet):
    """Adjust column widths based on dataframe contents."""
    for i, col in enumerate(df.columns):
        max_len = max(
            df[col].astype(str).apply(len).max(),
            len(str(col))
        ) + 2  # extra padding
        worksheet.set_column(i, i, max_len)

def write_formatted_sheet(writer, df, sheet_name):
    """
    Write df to Excel sheet with:
    - yellow background header with borders,
    - borders only on the Premium column cells,
    - auto-sized columns,
    - center-aligned values.
    """
    df.to_excel(writer, index=False, sheet_name=sheet_name)
    workbook  = writer.book
    worksheet = writer.sheets[sheet_name]

    # Header format: yellow fill, bold, border, centered
    header_format = workbook.add_format({
        "bold": True,
        "bg_color": "#FFFF00",
        "border": 1,
        "align": "center"
    })

    # Border format for Premium column cells: border + centered
    bordered_format = workbook.add_format({
        "border": 1,
        "align": "center"
    })

    # Format header cells
    for col_num, col_name in enumerate(df.columns.values):
        worksheet.write(0, col_num, col_name, header_format)

    # Find the index of the Premium column
    premium_col_idx = df.columns.get_loc("Premium")

    # Write Premium cells again with border format (keep data centered)
    for row in range(1, len(df) + 1):
        premium_value = df.iat[row - 1, premium_col_idx]
        worksheet.write(row, premium_col_idx, premium_value, bordered_format)

    # Auto-adjust column widths
    autosize_columns(df, worksheet)

def main():
    if len(sys.argv) < 2:
        print("Usage: python sort_by_premium.py <input_csv>")
        sys.exit(1)

    infile = sys.argv[1]
    if not os.path.exists(infile):
        print(f"File not found: {infile}")
        sys.exit(2)

    try:
        df = pd.read_csv(infile)
    except Exception as e:
        print(f"Error reading {infile}: {e}")
        sys.exit(3)

    before = len(df)

    # Remove duplicates by Symbol, Expiry, Strike, Side
    df = df.drop_duplicates(subset=["Symbol", "Expiry", "Strike", "Side"], keep="first")

    # Filter Premium >= MIN_PREMIUM
    df = df[df["Premium"] >= MIN_PREMIUM]

    # Separate CALL and PUT rows
    df_ce = df[df["Side"].str.contains("CALL", case=False, na=False)].copy()
    df_pe = df[df["Side"].str.contains("PUT", case=False, na=False)].copy()

    # Sort by Premium descending
    df_ce = df_ce.sort_values(by=["Premium"], ascending=False).reset_index(drop=True)
    df_pe = df_pe.sort_values(by=["Premium"], ascending=False).reset_index(drop=True)

    # Write to Excel file with two sheets
    excel_out = "Monthly_premium.xlsx"
    with pd.ExcelWriter(excel_out, engine="xlsxwriter") as writer:
        write_formatted_sheet(writer, df_ce, "CALL")
        write_formatted_sheet(writer, df_pe, "PUT")

    print(f"Processed {infile}")
    print(f"Removed {before - len(df)} rows (duplicates + Premium < {MIN_PREMIUM}).")
    print(f"Saved: {excel_out} (CALL={len(df_ce)} rows, PUT={len(df_pe)} rows)")

if __name__ == "__main__":
    main()
