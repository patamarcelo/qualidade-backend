const filterVariedades = plantio.map((data, i) => {
	return data.variedade__cultura__cultura;
});

const filterVariedadesDif = plantio.map((data, i) => {
	return `${data.variedade__cultura__cultura} - ${data.variedade__variedade}`;
});

const filterVar = ["Todas", ...filterVariedades];
const filterVarDif = ["Todas", ...filterVariedadesDif];

console.log(colheita);
var app = new Vue({
	delimiters: ["[[", "]]"],
	el: "#app",
	data: {
		message: "Hello Vue!",
		ciclos: ["1", "2", "3"],
		selectedCiclo: url.search.split("=")[1]
			? url.search.split("=")[1]
			: "1",
		selecredSafra: "2024/2025",
		safras: ["2022/2023", "2023/2024","2024/2025"],
		plantio: plantio,
		colheita: colheita,
		variedades: [...new Set(filterVar)],
		variedadesDif: [...new Set(filterVarDif)],
		filteredCutulre: "Todas",
		filteredCutulreDif: "",
		selected: "",
		viewAllVareidades: false,
		excludeFarm: [],
		style: {
			color: "whitesmoke",
			backgroundColor: "blue"
		},
		styleTitle: {
			color: "whitesmoke",
			backgroundColor: "grenn"
		},
		imageField: "soy"
	},
	methods: {
		navGo() {
			console.log("gogogo");
			window.location = this.customUrl;
		},
		resetPlantio() {
			this.plantio = plantio;
		},
		viewVaris() {
			console.log("Working");
			console.log(this.getFilteredChildren("Cervo"));
			this.viewAllVareidades = !this.viewAllVareidades;
		},
		greet: function (name) {
			console.log(this.excludeFarm);
			console.log(plantio);
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
			if (size < 25) {
				return "progress-bar bg-warning";
			}
			if (size < 80) {
				return "progress-bar bg-info";
			}
			return "progress-bar bg-success";
		}
	},
	watch: {
		excludeFarm() {
			if (this.excludeFarm.length > 0) {
				this.excludeFarm.map((data) => {
					console.log("excluiir a fazenda", data);
				});
			}
		},
		filteredCutulre() {
			if (this.filteredCutulre === "Todas") {
				console.log("todas", this.filteredCutulre);
				this.style.backgroundColor = "blue";
			}
			if (this.filteredCutulre === "Soja") {
				console.log("Soja", this.filteredCutulre);
				this.style.backgroundColor = "green";
			}
			if (this.filteredCutulre === "Feijão") {
				console.log("Feijão", this.filteredCutulre);
				this.style.backgroundColor = "rgb(119,63,27)";
			}
			if (this.filteredCutulre === "Arroz") {
				this.style.backgroundColor = "rgb(214, 220, 38)";
			}
			if (this.filteredCutulre === "Todas") {
				this.filteredCutulreDif = "";
			} else {
				console.log(
					"thisvar",
					this.variedadesDif
						.filter((data) =>
							data.includes(this.filteredCutulre)
						)[0]
						.split("-")[1]
						.trim()
				);
				this.filteredCutulreDif = this.variedadesDif
					.filter((data) => data.includes(this.filteredCutulre))[0]
					.split("-")[1]
					.trim();
			}
		}
	},
	computed: {
		customUrl() {
			return `/admin/diamante/plantiodetail/?ciclo=${this.selectedCiclo}&safra=${this.selecredSafra.replace('/','_')}`;
		},
		onlyFarmWhitoutVariedade() {
			const onlyFarmSetSOut = this.plantio.map((data) => {
				const name = data.talhao__fazenda__nome;
				return name;
			});
			return [...new Set(onlyFarmSetSOut)];
		},
		onlyFarm() {
			const onlyFarmSetS = this.plantio.map((data) => {
				console.log(data);
				const name =
					data.talhao__fazenda__nome +
					"|" +
					data.variedade__cultura__cultura;
				return name;
			});
			return [...new Set(onlyFarmSetS)];
		},
		titleAcomp() {
			if (this.filteredCutulreDif) {
				return this.filteredCutulreDif;
			}

			if (this.filteredCutulre !== "Todas") {
				return this.filteredCutulre;
			}

			return " ";
		},
		filteredArray() {
			let filtPlantio = [];
			if (this.excludeFarm.length > 0) {
				this.plantio = this.plantio.filter(
					(data) =>
						!this.excludeFarm.includes(data.talhao__fazenda__nome)
				);
			}
			if (this.filteredCutulreDif) {
				filtPlantio = this.plantio.filter(
					(data) =>
						data.variedade__variedade ===
						this.filteredCutulreDif.trim()
				);
			} else {
				filtPlantio = this.plantio;
			}
			const newDict = filtPlantio
				.filter((data) =>
					this.filteredCutulre == "Todas"
						? data.variedade__cultura__cultura !== "nenhuma"
						: data.variedade__cultura__cultura ===
						  this.filteredCutulre
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
								Number(curr.area_total) -
								Number(curr.area_finalizada),
							pesoColhido: 0,
							produtividade: 0
						};
					} else {
						acc[newObj]["areaTotal"] += Number(curr.area_total);
						acc[newObj]["areaColheita"] += Number(
							curr.area_finalizada
						);
						acc[newObj]["saldoColheita"] +=
							Number(curr.area_total) -
							Number(curr.area_finalizada);
					}
					return acc;
				}, {});

			let filtColheita = [];
			if (this.filteredCutulreDif) {
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
						newDict[nameDict]["pesoColhido"] += Number(
							filtColheita[i].peso_scs
						);
						newDict[nameDict]["produtividade"] =
							newDict[nameDict]["pesoColhido"] /
							Number(newDict[nameDict]["areaColheita"]);
					} else {
						newDict[nameDict]["pesoColhido"] = Number(
							filtColheita[i].peso_scs
						);
						newDict[nameDict]["produtividade"] =
							Number(filtColheita[i].peso_scs) /
							Number(newDict[nameDict]["areaColheita"]);
					}
				}
			}
			return newDict;
		},
		filteredArrayByVariedade() {
			let filtPlantio = [];
			if (this.filteredCutulreDif) {
				filtPlantio = this.plantio.filter(
					(data) =>
						data.variedade__variedade ===
						this.filteredCutulreDif.trim()
				);
			} else {
				filtPlantio = this.plantio;
			}
			const newDict = filtPlantio
				.filter((data) =>
					this.filteredCutulre == "Todas"
						? data.variedade__cultura__cultura !== "nenhuma"
						: data.variedade__cultura__cultura ===
						  this.filteredCutulre
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
								Number(curr.area_total) -
								Number(curr.area_finalizada),
							pesoColhido: 0,
							produtividade: 0
						};
					} else {
						acc[newObj]["areaTotal"] += Number(curr.area_total);
						acc[newObj]["areaColheita"] += Number(
							curr.area_finalizada
						);
						acc[newObj]["saldoColheita"] +=
							Number(curr.area_total) -
							Number(curr.area_finalizada);
					}
					return acc;
				}, {});

			let filtColheita = [];
			if (this.filteredCutulreDif) {
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
						newDict[nameDict]["pesoColhido"] += Number(
							filtColheita[i].peso_scs
						);
						newDict[nameDict]["produtividade"] =
							newDict[nameDict]["pesoColhido"] /
							Number(newDict[nameDict]["areaColheita"]);
					} else {
						newDict[nameDict]["pesoColhido"] = Number(
							filtColheita[i].peso_scs
						);
						newDict[nameDict]["produtividade"] =
							Number(filtColheita[i].peso_scs) /
							Number(newDict[nameDict]["areaColheita"]);
					}
				}
			}
			return newDict;
		},
		newTotals() {
			let newTotals = {};
			for (const [key, value] of Object.entries(this.filteredArray)) {
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
			var filteVar =
				this.filteredCutulre === "Todas"
					? this.variedadesDif
					: this.variedadesDif.filter((data) =>
							data.includes(this.filteredCutulre)
					  );
			return filteVar.map((data) => data.split("-")[1]);
		}
	}
});
