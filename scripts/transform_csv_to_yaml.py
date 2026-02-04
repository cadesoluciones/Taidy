import argparse
import csv
import re
import sys
import yaml


def clean_name(description: str) -> str:
    """
    Generates a snake_case name from the description.
    Example: "JobHeader API" -> "bc_job_header"
    """
    if not description:
        return "bc_unknown_table"

    # Remove " API" suffix (case insensitive)
    name = re.sub(r"\s+API$", "", description, flags=re.IGNORECASE)

    # Replace non-alphanumeric characters with underscores
    name = re.sub(r"[^a-zA-Z0-9]", "_", name)

    # CamelCase to snake_case conversion
    # Handle consecutive capitals (e.g., XMLHttp -> xml_http)
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    # Remove multiple underscores and leading/trailing underscores
    name = re.sub(r"_+", "_", name).strip("_")

    return f"bc_{name}"


def transform_csv_to_yaml(input_path: str, output_path: str):
    tables = []
    base_api_url = None

    try:
        with open(input_path, "r", encoding="utf-8-sig") as f:
            # The provided CSV seems to have quoted fields and spaces after commas.
            # skipinitialspace=True helps with spaces after delimiters.
            reader = csv.DictReader(f, skipinitialspace=True)

            # Normalize headers (remove quotes if they are part of the key somehow,
            # though DictReader usually handles quotes in the header line itself)
            # Inspecting the header from the user prompt: "Tipo de llamada", "Codigo", ...
            # csv.DictReader should parse "Tipo de llamada" as the key.

            for row_num, row in enumerate(reader, 1):
                # Columns: "Descripción", "Columna 7" (URL), "Referencia"

                # Strip keys and values just in case
                row = {k.strip(): v.strip() for k, v in row.items() if k}

                description = row.get("Descripción", "")
                url = row.get("Columna 7", "")

                # Skip empty rows or rows without URL
                if not url or not description:
                    print(f"Skipping row {row_num}: Missing Description or URL.")
                    continue

                name = clean_name(description)
                if "/" in url:
                    candidate_base, api_path = url.rsplit("/", 1)
                else:
                    print(f"Skipping row {row_num}: URL does not contain '/'.")
                    continue

                if base_api_url is None:
                    base_api_url = candidate_base
                elif base_api_url != candidate_base:
                    print(
                        f"Skipping row {row_num}: URL base does not match "
                        f"'{base_api_url}'."
                    )
                    continue

                table_entry = {
                    "name": name,
                    "description": description,
                    "api_path": api_path,
                    "incremental": True,  # Defaulting to True based on existing tables.yaml
                }
                tables.append(table_entry)

    except FileNotFoundError:
        print(f"Error: Input file '{input_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing CSV: {e}")
        sys.exit(1)

    if not base_api_url:
        print("Error: Could not determine base_api_url from input CSV.")
        sys.exit(1)

    output_data = {"base_api_url": base_api_url, "tables": tables}

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(
                output_data,
                f,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )
        print(f"Successfully converted {len(tables)} tables to '{output_path}'.")
    except Exception as e:
        print(f"Error writing YAML: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Transform Business Central table CSV to YAML config."
    )
    parser.add_argument("input_csv", help="Path to the source CSV file.")
    parser.add_argument("output_yaml", help="Path to the destination YAML file.")

    args = parser.parse_args()

    transform_csv_to_yaml(args.input_csv, args.output_yaml)


if __name__ == "__main__":
    main()
