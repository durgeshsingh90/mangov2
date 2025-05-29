import schemer
import json
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import logging
from pydantic import BaseModel
import txn_sender


logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up CORS
origins = [
    "http://",  # Assuming you are calling from this origin
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

class Parser(BaseModel):
    msg: str
    label: str

class Txn(BaseModel):
    msg: str
    label: str

class Config(BaseModel):
    ip: str
    port: str
    tps: str
    wait: str
    len: str

class SaveTxn(BaseModel):
    test: str
    testcase: str
    txn: str

class AddTest(BaseModel):
    name: str


s = schemer.Schemer()
s.load_schemas()

@app.get("/favicon.ico", include_in_schema=False)
async def get_favicon():
    return FileResponse("static/favicon.png")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        return FileResponse("main.html")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

@app.get("/config", response_class=HTMLResponse)
async def read_config():
    try:
        return FileResponse("config.html")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

@app.post("/read_json")
def read_json():
    try:
        config_file = "test_cases.json"
        with open(config_file, "r") as json_file:
            file = json.load(json_file)
    except Exception as e:
        return {"error": str(e)}

    try:
        config_file = "test_cases.json"
        with open(config_file, "r") as json_file:
            file = json.load(json_file)
    except Exception as e:
        return {"error": str(e)}

    logging.info(file)

    return {"result": file}

@app.post("/save_txn")
def save_txn(data:SaveTxn):
    saved = False
    try:
        config_file = "test_cases.json"
        with open(config_file, "r") as json_file:
            file = json.load(json_file)
    except Exception as e:
        return {"result": str(e)}

    for key in file:
        for ch_key in file[key]:
            if ch_key == data.testcase and key == data.test:
                file[key][ch_key] = data.txn
                saved = True
                break

    if not saved:
        try:
            file[data.test][data.testcase] = data.txn
        except:
            file[data.test] = {}
            if data.testcase != "":
                file[data.test][data.testcase] = data.txn

    try:
        config_file = "test_cases.json"
        with open(config_file, "w") as json_file:
            json.dump(file, json_file, indent=4)
    except Exception as e:
        return {"result": str(e)}

    config_file = "test_cases.json"
    with open(config_file, "r") as json_file:
        file = json.load(json_file)

    with open(config_file, "r") as json_file:
        file = json.load(json_file)

    return {"result": "Testcase has been saved"}

@app.post("/add_test")
def add_test(data:AddTest):
    try:
        config_file = "test_cases.json"
        with open(config_file, "r") as json_file:
            file = json.load(json_file)
    except Exception as e:
        return {"result": str(e)}

    file[data.name] = {}

    try:
        config_file = "test_cases.json"
        with open(config_file, "w") as json_file:
            json.dump(file, json_file, indent=4)
    except Exception as e:
        return {"result": str(e)}

    config_file = "test_cases.json"
    with open(config_file, "r") as json_file:
        file = json.load(json_file)

    return {"result": str(data.name + "has been added")}

@app.post("/get_config")
def get_config():
    try:
        config_file = "config.json"
        with open(config_file, "r") as json_file:
            con = json.load(json_file)
    except Exception as e:
        return {"result": str(e)}

    return {"result": con}

@app.post("/parser_raw")
def parser_raw(data:Parser):
    try:
        msg = s.parse(bytes.fromhex(data.msg), data.label)
    except Exception as e:
        return {"result": str(e)}

    return {"result": msg[0]}

@app.post("/parser_json")
def parser_json(data:Parser):
    try:
        raw = s.build(json.loads(data.msg), data.label)
    except Exception as e:
        return {"result": str(e)}
    return {"result": bytes.hex(raw)}

@app.post("/txn_send")
def txn_send(data:Txn):
    try:
        config_file = "config.json"
        with open(config_file, "r") as json_file:
            con = json.load(json_file)
    except Exception as e:
        logging.error("COULD NOT READ CONFIG")
        return {"result": str(e)}

    con["requests"] = [bytes.fromhex(data.msg)]

    len_ind = con["len_ind"]
    with open("len_ind_cnfg.json", "r") as f:
        con["len_ind"] = json.load(f)[len_ind]["len_ind"]

    output_msg = ""
    a = ""
    try:
        t = txn_sender.TxnSender(con["ip"],
                                 int(con["port"]),
                                 con["requests"],
                                 con["len_ind"],
                                 None,
                                 0,
                                 200,
                                 int(con["tps"]),
                                 int(con["wait_after"]),
                                 )
        output_msg = t.run(s)
        o = []
        a = s.parse(output_msg[0], data.label)
        o.append(a)

    except Exception as e:
        logging.error("COULD NOT SEND")
        return {"result": str(e), "data": []}

    return {"result": "Txn has been sent", "data": ["input_msg[0]", o]}

@app.post("/save_config")
def save_config(data:Config):
    try:
        config_file = "config.json"
        with open(config_file, "r") as json_file:
            con = json.load(json_file)
    except Exception as e:
        return {"result": str(e)}

    con["ip"] = data.ip
    con["port"] = data.port
    con["tps"] = data.tps
    con["wait_after"] = data.wait
    con["len_ind"] = data.len

    try:
        config_file = "config.json"
        with open(config_file, "w") as json_file:
            json.dump(con, json_file, indent=4)
    except Exception as e:
        return {"result": str(e)}

    return {"result": "config saved."}

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5001, log_level="info")
