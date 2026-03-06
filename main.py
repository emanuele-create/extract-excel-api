from fastapi import FastAPI, UploadFile, File, HTTPException
import pandas as pd
from io import BytesIO

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/processar-planilha")
async def processar_planilha(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .xlsx")

    try:
        content = await file.read()

        df = pd.read_excel(
            BytesIO(content),
            skiprows=2,
            engine="openpyxl"
        )

        df.columns = df.columns.astype(str).str.strip()

        mask = df.fillna("").astype(str).apply(
            lambda row: row.str.strip().str.contains(
                r"Total\s+de\s+Itens",
                case=False,
                regex=True
            ).any(),
            axis=1
        )

        if mask.any():
            idx = mask.idxmax()
            pos = df.index.get_loc(idx)
            df = df.iloc[:pos]

        required_columns = ["Paciente/Fornecedor", "Crédito", "Data"]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Colunas não encontradas: {missing}. Colunas disponíveis: {df.columns.tolist()}"
            )

        df = df[required_columns]
        df = df.dropna(how="all").reset_index(drop=True)

        return df.to_dict(orient="records")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar a planilha: {str(e)}")