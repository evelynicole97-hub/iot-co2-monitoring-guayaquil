import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import pandas as pd
from influxdb_client import InfluxDBClient
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

# ================= CONFIGURACIÓN =================
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "TOKEN"
INFLUX_ORG = "universidad"
INFLUX_BUCKET = "co2_monitoring"
INFLUX_MEASUREMENT = "co2"
INFLUX_FIELD = "co2_ppm"
CO2_THRESHOLD = 1000
UPDATE_INTERVAL_MS = 300000  # 5 minutos


class CO2MonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema IoT de Monitoreo de CO₂")
        self.root.geometry("1200x760")
        self.data = pd.DataFrame()
        self.running = True
        self.client = None
        self.query_api = None
        self._styles()
        self._interface()
        self.connect_influxdb()
        self.root.after(1000, self.update_data)
        self.root.after(UPDATE_INTERVAL_MS, self.periodic_update)
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

    def _styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("Value.TLabel", font=("Segoe UI", 24, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))

    def _interface(self):
        header = ttk.Frame(self.root, padding=(20, 15))
        header.pack(fill="x")
        ttk.Label(header, text="Monitoreo IoT de dióxido de carbono (CO₂)", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Aula y Laboratorio | Datos almacenados en InfluxDB", style="Subtitle.TLabel").pack(anchor="w")

        controls = ttk.Frame(self.root, padding=(20, 5))
        controls.pack(fill="x")
        ttk.Label(controls, text="Período:").pack(side="left")
        self.period_var = tk.StringVar(value="24")
        ttk.Combobox(controls, textvariable=self.period_var,
                     values=["1", "6", "12", "24", "48", "72", "168"],
                     width=8, state="readonly").pack(side="left", padx=5)
        ttk.Label(controls, text="horas").pack(side="left")
        ttk.Button(controls, text="Actualizar", command=self.update_data).pack(side="left", padx=10)
        ttk.Button(controls, text="Exportar CSV", command=self.export_csv).pack(side="left", padx=5)
        self.connection_label = ttk.Label(controls, text="● Sin conexión", style="Status.TLabel")
        self.connection_label.pack(side="right")

        cards = ttk.Frame(self.root, padding=(20, 10))
        cards.pack(fill="x")
        self.aula_value = self.create_card(cards, "AULA")
        self.lab_value = self.create_card(cards, "LABORATORIO")
        self.avg_value = self.create_card(cards, "PROMEDIO")
        self.alert_value = self.create_card(cards, "ALERTAS > 1000 ppm")

        graph_frame = ttk.LabelFrame(self.root, text="Evolución de la concentración de CO₂", padding=10)
        graph_frame.pack(fill="both", expand=True, padx=20, pady=(5, 10))
        self.figure = Figure(figsize=(10, 4.5), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel("Fecha y hora")
        self.ax.set_ylabel("CO₂ (ppm)")
        self.ax.grid(True, alpha=0.25)
        self.canvas = FigureCanvasTkAgg(self.figure, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.draw()

        table_frame = ttk.LabelFrame(self.root, text="Registros recientes", padding=8)
        table_frame.pack(fill="both", padx=20, pady=(0, 15))
        columns = ("timestamp", "device", "space", "co2")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=7)
        for col, title, width in [("timestamp", "Fecha / hora", 190), ("device", "Nodo", 150), ("space", "Espacio", 150), ("co2", "CO₂ (ppm)", 100)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        footer = ttk.Frame(self.root, padding=(20, 5))
        footer.pack(fill="x")
        self.status_var = tk.StringVar(value="Esperando datos...")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left")
        ttk.Label(footer, text="Umbral operativo: 1000 ppm").pack(side="right")

    def create_card(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, padding=(15, 10))
        frame.pack(side="left", fill="both", expand=True, padx=5)
        label = ttk.Label(frame, text="Sin datos", style="Value.TLabel")
        label.pack(pady=5)
        return label

    def connect_influxdb(self):
        try:
            if INFLUX_TOKEN == "TOKEN":
                self.connection_label.config(text="● Configure el token")
                self.status_var.set("Configure INFLUX_TOKEN en app.py")
                return False
            self.client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=10000)
            self.query_api = self.client.query_api()
            if self.client.health().status == "pass":
                self.connection_label.config(text="● InfluxDB conectado")
                return True
        except Exception as e:
            self.connection_label.config(text="● Error de conexión")
            self.status_var.set(f"Error de conexión: {e}")
        return False

    def build_flux_query(self, hours):
        return f'''from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r["_measurement"] == "{INFLUX_MEASUREMENT}")
  |> filter(fn: (r) => r["_field"] == "{INFLUX_FIELD}")
  |> filter(fn: (r) => r["space"] == "Aula" or r["space"] == "Laboratorio")
  |> keep(columns: ["_time", "_value", "device", "space"])
  |> sort(columns: ["_time"], desc: true)'''

    def query_data(self):
        if self.query_api is None and not self.connect_influxdb():
            return pd.DataFrame()
        try:
            hours = int(self.period_var.get())
            tables = self.query_api.query(query=self.build_flux_query(hours), org=INFLUX_ORG)
            rows = []
            for table in tables:
                for record in table.records:
                    rows.append({
                        "timestamp": record.get_time(),
                        "co2": float(record.get_value()),
                        "device": record.values.get("device", "N/D"),
                        "space": record.values.get("space", "N/D")
                    })
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows)
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            return df.dropna(subset=["timestamp", "co2"]).sort_values("timestamp")
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Error consultando InfluxDB: {e}"))
            return pd.DataFrame()

    def update_data(self):
        if not self.running:
            return
        self.status_var.set("Consultando datos de InfluxDB...")
        threading.Thread(target=self.load_data_thread, daemon=True).start()

    def load_data_thread(self):
        df = self.query_data()
        self.root.after(0, lambda: self.process_loaded_data(df))

    def process_loaded_data(self, df):
        if df.empty:
            self.status_var.set("No se encontraron registros para el período seleccionado.")
            return
        self.data = df
        self.update_cards()
        self.update_graph()
        self.update_table()
        last_time = df["timestamp"].max()
        self.status_var.set(f"{len(df)} registros | Último registro: {last_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.connection_label.config(text="● InfluxDB conectado")

    def periodic_update(self):
        if self.running:
            self.update_data()
            self.root.after(UPDATE_INTERVAL_MS, self.periodic_update)

    def update_cards(self):
        latest = self.data.sort_values("timestamp").groupby("space").tail(1)
        aula = latest[latest["space"].str.lower() == "aula"]
        lab = latest[latest["space"].str.lower() == "laboratorio"]
        self.aula_value.config(text=f"{aula.iloc[0]['co2']:.0f} ppm" if not aula.empty else "Sin datos")
        self.lab_value.config(text=f"{lab.iloc[0]['co2']:.0f} ppm" if not lab.empty else "Sin datos")
        self.avg_value.config(text=f"{self.data['co2'].mean():.0f} ppm")
        self.alert_value.config(text=str(int((self.data["co2"] > CO2_THRESHOLD).sum())))

    def update_graph(self):
        self.ax.clear()
        for space in ["Aula", "Laboratorio"]:
            subset = self.data[self.data["space"].str.lower() == space.lower()].sort_values("timestamp")
            if not subset.empty:
                self.ax.plot(subset["timestamp"], subset["co2"], marker=".", markersize=2, linewidth=1.2, label=space)
        self.ax.axhline(CO2_THRESHOLD, linestyle="--", linewidth=1.2, label="Umbral 1000 ppm")
        self.ax.set_title("Evolución de la concentración de CO₂")
        self.ax.set_xlabel("Fecha y hora")
        self.ax.set_ylabel("CO₂ (ppm)")
        self.ax.grid(True, alpha=0.25)
        self.ax.legend(loc="upper left")
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
        self.figure.autofmt_xdate()
        self.figure.tight_layout()
        self.canvas.draw()

    def update_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for _, row in self.data.sort_values("timestamp", ascending=False).head(30).iterrows():
            self.tree.insert("", "end", values=(
                row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                row["device"], row["space"], f"{row['co2']:.0f}"
            ))

    def export_csv(self):
        if self.data.empty:
            messagebox.showwarning("Sin datos", "No existen datos para exportar.")
            return
        filename = filedialog.asksaveasfilename(
            title="Guardar datos de CO₂", defaultextension=".csv",
            filetypes=[("Archivo CSV", "*.csv"), ("Todos los archivos", "*.*")]
        )
        if not filename:
            return
        try:
            export_df = self.data.copy()
            export_df["timestamp"] = export_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
            export_df.to_csv(filename, index=False, encoding="utf-8-sig")
            messagebox.showinfo("Exportación completada", f"Datos exportados correctamente:\n\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", f"No fue posible exportar los datos:\n{e}")

    def close_app(self):
        self.running = False
        if self.client:
            self.client.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = CO2MonitorApp(root)
    root.mainloop()
