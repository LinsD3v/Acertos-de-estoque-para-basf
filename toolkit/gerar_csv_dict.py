import pandas as pd

arquivo_entrada = "C.csv"
arquivo_saida = "relacao_sku_basf_codigo_gix.csv"

# Leitura
df = pd.read_csv(
    arquivo_entrada,
    sep=";",
    encoding="utf-8",
    encoding_errors="replace",
    skipinitialspace=True,
    dtype={"SkuId Vtex Basf": "string"}
)

# Limpa espaços dos cabeçalhos  
df.columns = df.columns.str.strip()

# Mostra os cabeçalhos encontrados
print("Colunas:", df.columns.tolist())

# Localiza as colunas pelo nome, sem depender dos acentos
colunas = {
    "GIX": next(c for c in df.columns if c.upper().startswith("C")),
    "SKU_VTEX": next(c for c in df.columns if c.upper().startswith("SKU")),
    "NOME": next(c for c in df.columns if c.upper().startswith("DESCRI"))
}

# Monta o resultado
resultado = pd.DataFrame({
    "GIX": df[colunas["GIX"]].astype(str).str.strip(),
    "SKU_VTEX": df[colunas["SKU_VTEX"]],
    "NOME": df[colunas["NOME"]].str.strip()
})

# Trata SKU vazio
resultado["SKU_VTEX"] = resultado["SKU_VTEX"].fillna("Null")

# Exporta
resultado.to_csv(
    arquivo_saida,
    sep=";",
    index=False,
    encoding="utf-8-sig"
)

print(f"Conversão concluída! {len(resultado)} registros exportados.")
