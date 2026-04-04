const filterVariedades = plantio.map((data) => {
	return data.variedade__cultura__cultura;
});

const filterVariedadesDif = plantio.map((data) => {
	return `${data.variedade__cultura__cultura} - ${data.variedade__variedade}`;
});

const filterVar = ["Todas", ...filterVariedades];
const filterVarDif = ["Todas", ...filterVariedadesDif];

const currentUrl = new URL(window.location.href);
const getParam = (key, fallback = "") => currentUrl.searchParams.get(key) || fallback;

var app = new Vue({
	delimiters: ["[[", "]]"],
	el: "#app",
	data: {
		generatedAt: new Date().toLocaleString("pt-BR"),
		message: "Hello Vue!",
		ciclos: ["1", "2", "3"],
		selectedCiclo: getParam("ciclo", ""),
		selecredSafra: getParam("safra", "").replace("_", "/"),
		safras: ["2022/2023", "2023/2024", "2024/2025", "2025/2026", "2026/2027"],

		createdAtGte: getParam("created_at_gte", ""),
		createdAtLte: getParam("created_at_lte", ""),
		dataGte: getParam("data_gte", ""),
		dataLte: getParam("data_lte", ""),

		plantioOriginal: [...plantio],
		plantio: [...plantio],
		colheita: colheita,

		variedades: [...new Set(filterVar)],
		variedadesDif: [...new Set(filterVarDif)],

		filteredCutulre: "Todas",
		filteredCutulreDif: "Todas",
		selected: "",
		viewAllVareidades: false,
		excludeFarm: [],

		isSubmittingFilter: false,
		isClearingFilter: false,

		style: {
			color: "whitesmoke",
			backgroundColor: "blue"
		},
		styleTitle: {
			color: "whitesmoke",
			backgroundColor: "green"
		},
		imageField: "soy",
		disabledBtn: true,
	},
	methods: {
		navGo() {
			if (this.disabledBtn || this.isSubmittingFilter) return;
			this.isSubmittingFilter = true;
			window.location = this.customUrl;
		},

		formatDate(dateStr) {
			if (!dateStr) return "";

			const [y, m, d] = dateStr.split("-");
			return `${d}/${m}/${y}`;
		},
		clearFilters() {
			if (this.isClearingFilter) return;
			this.isClearingFilter = true;
			window.location = "/admin/diamante/plantiodetail/";
		},

		resetPlantio() {
			this.excludeFarm = [];
			this.plantio = [...this.plantioOriginal];
		},

		viewVaris() {
			this.viewAllVareidades = !this.viewAllVareidades;
		},

		greet() {
			console.log(this.excludeFarm);
			console.log(this.plantio);
		},

		customIcon(cultura) {
			if (cultura === "Soja") {
				return "/static/images/icons/soy.png";
			}
			if (cultura === "Feijão") {
				return "/static/images/icons/beans2.png";
			}
			if (cultura === "Arroz") {
				return "/static/images/icons/rice.png";
			}
			if (cultura === "Algodão") {
				return "/static/images/icons/cotton.png";
			}
			return "";
		},

		getFilteredChildren(filter) {
			console.log(filter);
			console.log(this.filteredArrayByVariedade);
			return "teste 1 ";
		},

		getwidth(size) {
			return `width: ${size}% ; background-color: yellow`;
		},

		getClass(size) {
			if (Number(size) < 25) {
				return "progress-bar bg-warning";
			}
			if (Number(size) < 80) {
				return "progress-bar bg-info";
			}
			return "progress-bar bg-success";
		},

		updateDisabledButton() {
			this.disabledBtn = !(this.selectedCiclo.length > 0 && this.selecredSafra.length > 0);
		}
	},

	watch: {
		selectedCiclo() {
			this.updateDisabledButton();
		},

		selecredSafra() {
			this.updateDisabledButton();
		},

		excludeFarm() {
			if (this.excludeFarm.length > 0) {
				this.excludeFarm.map((data) => {
					console.log("excluir a fazenda", data);
				});
			}
		},

		filteredCutulre() {
			if (this.filteredCutulre === "Todas") {
				this.style.backgroundColor = "blue";
				this.filteredCutulreDif = "Todas";
				return;
			}

			if (this.filteredCutulre === "Soja") {
				this.style.backgroundColor = "green";
			}
			if (this.filteredCutulre === "Feijão") {
				this.style.backgroundColor = "rgb(119,63,27)";
			}
			if (this.filteredCutulre === "Arroz") {
				this.style.backgroundColor = "rgb(214, 220, 38)";
			}

			const variedadesDaCultura = this.filterVariedadesDif.filter(
				(data) => data !== "Todas" && data.includes(this.filteredCutulre)
			);

			if (
				this.filteredCutulreDif === "Todas" ||
				!variedadesDaCultura.some((item) => item.split("-")[1]?.trim() === this.filteredCutulreDif)
			) {
				const firstVariedade = variedadesDaCultura[0];

				if (firstVariedade && firstVariedade.includes("-")) {
					this.filteredCutulreDif = firstVariedade.split("-")[1].trim();
				} else {
					this.filteredCutulreDif = "Todas";
				}
			}
		}
	},

	computed: {
		customUrl() {
			const params = new URLSearchParams();

			if (this.selectedCiclo) {
				params.set("ciclo", this.selectedCiclo);
			}

			if (this.selecredSafra) {
				params.set("safra", this.selecredSafra.replace("/", "_"));
			}

			if (this.createdAtGte) {
				params.set("created_at_gte", this.createdAtGte);
			}

			if (this.createdAtLte) {
				params.set("created_at_lte", this.createdAtLte);
			}

			if (this.dataGte) {
				params.set("data_gte", this.dataGte);
			}

			if (this.dataLte) {
				params.set("data_lte", this.dataLte);
			}

			return `/admin/diamante/plantiodetail/?${params.toString()}`;
		},

		onlyFarmWhitoutVariedade() {
			const sourcePlantio = this.plantioOriginal || [];
			const onlyFarmSetSOut = sourcePlantio.map((data) => {
				return data.talhao__fazenda__nome;
			});
			return [...new Set(onlyFarmSetSOut)];
		},

		onlyFarm() {
			const sourcePlantio = this.filteredPlantioBase;
			const onlyFarmSetS = sourcePlantio.map((data) => {
				const name =
					data.talhao__fazenda__nome +
					"|" +
					data.variedade__cultura__cultura;
				return name;
			});
			return [...new Set(onlyFarmSetS)];
		},

		titleAcomp() {
			if (this.filteredCutulreDif && this.filteredCutulreDif !== "Todas") {
				return this.filteredCutulreDif;
			}

			if (this.filteredCutulre !== "Todas") {
				return this.filteredCutulre;
			}

			return " ";
		},

		filteredPlantioBase() {
			let base = [...this.plantioOriginal];

			if (this.excludeFarm.length > 0) {
				base = base.filter(
					(data) => !this.excludeFarm.includes(data.talhao__fazenda__nome)
				);
			}

			return base;
		},

		filteredArray() {
			let filtPlantio = [];

			if (this.filteredCutulreDif && this.filteredCutulreDif !== "Todas") {
				filtPlantio = this.filteredPlantioBase.filter(
					(data) => data.variedade__variedade === this.filteredCutulreDif.trim()
				);
			} else {
				filtPlantio = this.filteredPlantioBase;
			}

			const newDict = filtPlantio
				.filter((data) =>
					this.filteredCutulre === "Todas"
						? data.variedade__cultura__cultura !== "nenhuma"
						: data.variedade__cultura__cultura === this.filteredCutulre
				)
				.reduce((acc, curr) => {
					const newObj =
						curr.talhao__fazenda__nome +
						"|" +
						curr.variedade__cultura__cultura;

					if (!acc[newObj]) {
						acc[newObj] = {
							variedade: curr.variedade__cultura__cultura,
							areaTotal: Number(curr.area_total),
							areaColheita: Number(curr.area_finalizada),
							saldoColheita:
								Number(curr.area_total) - Number(curr.area_finalizada),
							pesoColhido: 0,
							produtividade: 0
						};
					} else {
						acc[newObj]["areaTotal"] += Number(curr.area_total);
						acc[newObj]["areaColheita"] += Number(curr.area_finalizada);
						acc[newObj]["saldoColheita"] +=
							Number(curr.area_total) - Number(curr.area_finalizada);
					}
					return acc;
				}, {});

			let filtColheita = [];

			if (this.filteredCutulreDif && this.filteredCutulreDif !== "Todas") {
				filtColheita = this.colheita.filter(
					(data) =>
						data.plantio__variedade__variedade ===
						this.filteredCutulreDif.trim()
				);
			} else {
				filtColheita = this.colheita;
			}

			for (let i = 0; i < filtColheita.length; i++) {
				const nameDict =
					`${filtColheita[i]["plantio__talhao__fazenda__nome"]}` +
					"|" +
					`${filtColheita[i]["plantio__variedade__cultura__cultura"]}`;

				if (newDict[nameDict]) {
					if (newDict[nameDict]["pesoColhido"] > 0) {
						newDict[nameDict]["pesoColhido"] += Number(filtColheita[i].peso_scs);
						newDict[nameDict]["produtividade"] =
							newDict[nameDict]["pesoColhido"] /
							Number(newDict[nameDict]["areaColheita"] || 0);
					} else {
						newDict[nameDict]["pesoColhido"] = Number(filtColheita[i].peso_scs);
						newDict[nameDict]["produtividade"] =
							Number(filtColheita[i].peso_scs) /
							Number(newDict[nameDict]["areaColheita"] || 0);
					}
				}
			}

			return newDict;
		},

		filteredArrayByVariedade() {
			let filtPlantio = [];

			if (this.filteredCutulreDif && this.filteredCutulreDif !== "Todas") {
				filtPlantio = this.filteredPlantioBase.filter(
					(data) => data.variedade__variedade === this.filteredCutulreDif.trim()
				);
			} else {
				filtPlantio = this.filteredPlantioBase;
			}

			const newDict = filtPlantio
				.filter((data) =>
					this.filteredCutulre === "Todas"
						? data.variedade__cultura__cultura !== "nenhuma"
						: data.variedade__cultura__cultura === this.filteredCutulre
				)
				.reduce((acc, curr) => {
					const newObj =
						curr.talhao__fazenda__nome +
						"|" +
						curr.variedade__cultura__cultura +
						"|" +
						curr.variedade__variedade;

					if (!acc[newObj]) {
						acc[newObj] = {
							cultura: curr.variedade__cultura__cultura,
							variedade: curr.variedade__variedade,
							areaTotal: Number(curr.area_total),
							areaColheita: Number(curr.area_finalizada),
							saldoColheita:
								Number(curr.area_total) - Number(curr.area_finalizada),
							pesoColhido: 0,
							produtividade: 0
						};
					} else {
						acc[newObj]["areaTotal"] += Number(curr.area_total);
						acc[newObj]["areaColheita"] += Number(curr.area_finalizada);
						acc[newObj]["saldoColheita"] +=
							Number(curr.area_total) - Number(curr.area_finalizada);
					}
					return acc;
				}, {});

			let filtColheita = [];

			if (this.filteredCutulreDif && this.filteredCutulreDif !== "Todas") {
				filtColheita = this.colheita.filter(
					(data) =>
						data.plantio__variedade__variedade ===
						this.filteredCutulreDif.trim()
				);
			} else {
				filtColheita = this.colheita;
			}

			for (let i = 0; i < filtColheita.length; i++) {
				const nameDict =
					`${filtColheita[i]["plantio__talhao__fazenda__nome"]}` +
					"|" +
					`${filtColheita[i]["plantio__variedade__cultura__cultura"]}` +
					"|" +
					`${filtColheita[i]["plantio__variedade__variedade"]}`;

				if (newDict[nameDict]) {
					if (newDict[nameDict]["pesoColhido"] > 0) {
						newDict[nameDict]["pesoColhido"] += Number(filtColheita[i].peso_scs);
						newDict[nameDict]["produtividade"] =
							newDict[nameDict]["pesoColhido"] /
							Number(newDict[nameDict]["areaColheita"] || 0);
					} else {
						newDict[nameDict]["pesoColhido"] = Number(filtColheita[i].peso_scs);
						newDict[nameDict]["produtividade"] =
							Number(filtColheita[i].peso_scs) /
							Number(newDict[nameDict]["areaColheita"] || 0);
					}
				}
			}

			return newDict;
		},

		newTotals() {
			let newTotals = {};

			for (const [, value] of Object.entries(this.filteredArray)) {
				if (!newTotals["areaColhida"]) {
					newTotals["areaColhida"] = value.areaColheita;
				} else {
					newTotals["areaColhida"] += value.areaColheita;
				}

				if (!newTotals["areaTotal"]) {
					newTotals["areaTotal"] = value.areaTotal;
				} else {
					newTotals["areaTotal"] += value.areaTotal;
				}

				if (!newTotals["saldoColheita"]) {
					newTotals["saldoColheita"] = value.saldoColheita;
				} else {
					newTotals["saldoColheita"] += value.saldoColheita;
				}

				if (!newTotals["pesoColhido"]) {
					newTotals["pesoColhido"] = Number(value.pesoColhido);
				} else {
					newTotals["pesoColhido"] += Number(value.pesoColhido);
				}
			}

			return newTotals;
		},

		filterVariedadesDif() {
			const filteVar =
				this.filteredCutulre === "Todas"
					? this.variedadesDif
					: this.variedadesDif.filter((data) =>
						data === "Todas" || data.includes(this.filteredCutulre)
					);

			return filteVar
				.map((data) => {
					if (!data) return "";
					if (data === "Todas") return "Todas";

					const parts = data.split("-");
					return parts.length > 1 ? parts[1].trim() : data;
				})
				.filter(Boolean);
		}
	},

	mounted() {
		this.updateDisabledButton();
		if (!this.filteredCutulreDif) {
			this.filteredCutulreDif = "Todas";
		}
	}
});