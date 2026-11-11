from backend.stock_processor import (
    OUTPUT_CSV,
    build_vtex_stock_file,
    save_outputs,
)


def main() -> None:
    vtex_frame = build_vtex_stock_file()
    save_outputs(vtex_frame)
    print(f"Arquivo gerado: {OUTPUT_CSV}")
    print(f"Registros procesados: {len(vtex_frame)}")


if __name__ == "__main__":
    main()
