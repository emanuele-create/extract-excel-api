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

        def limpar_cpf(cpf: str) -> str:
            return "".join(filter(str.isdigit, cpf))

        def cpf_valido(cpf: str) -> bool:
            cpf = limpar_cpf(cpf)

            # 1) precisa ter 11 dígitos
            if len(cpf) != 11:
                return False

            # 2) bloqueia CPFs com todos os dígitos iguais
            if cpf == cpf[0] * 11:
                return False

            # 3) valida 1º dígito verificador
            soma1 = sum(int(cpf[i]) * (10 - i) for i in range(9))
            digito1 = (soma1 * 10) % 11
            digito1 = 0 if digito1 == 10 else digito1

            # 4) valida 2º dígito verificador
            soma2 = sum(int(cpf[i]) * (11 - i) for i in range(10))
            digito2 = (soma2 * 10) % 11
            digito2 = 0 if digito2 == 10 else digito2

            return cpf[-2:] == f"{digito1}{digito2}"


        def nome_valido(nome: str) -> bool:
            if not nome:
                return False

            nome = nome.strip()

            # nome vazio depois do strip
            if not nome:
                return False

            # regra simples: precisa ter ao menos 2 caracteres
            if len(nome) < 2:
                return False

            return True


        CPF_NAO_ENCONTRADO = "CPF não encontrado"

        def extrair_nome_cpf(texto):
            if pd.isna(texto):
                return "", CPF_NAO_ENCONTRADO

            texto = str(texto).strip()
            if not texto:
                return "", CPF_NAO_ENCONTRADO

            partes = texto.rsplit(" - ", 1)
            if len(partes) != 2:
                return texto, CPF_NAO_ENCONTRADO

            nome = partes[0].strip()
            cpf = limpar_cpf(partes[1].strip())

            if not cpf_valido(cpf):
                return nome, CPF_NAO_ENCONTRADO

            return nome, cpf


        # aplica na coluna e expande a tupla para 2 colunas
        df[["nome_paciente", "cpf"]] = df["Paciente/Fornecedor"].apply(
            lambda texto: pd.Series(extrair_nome_cpf(texto))
        )

        df = df.drop(columns=["Paciente/Fornecedor"])
        df = df.rename(columns={"Crédito": "valor", "Data": "data"})

        df["data"] = pd.to_datetime(df["data"], dayfirst=True).dt.strftime("%d/%m/%Y")
        df["valor"] = df["valor"].apply(lambda v: int(v) if v == int(v) else v)

        return [{"pacientes": df.to_dict(orient="records")}]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar a planilha: {str(e)}")