const filterVariedades = plantio.map((data, i) => {
	return data.variedade__cultura__cultura;
});

const filterVariedadesDif = plantio.map((data, i) => {
	return `${data.variedade__cultura__cultura} - ${data.variedade__variedade}`;
});

const filterVar = ["Todas", ...filterVariedades];
const filterVarDif = ["Todas", ...filterVariedadesDif];

var app = new Vue({
	delimiters: ["[[", "]]"],
	el: "#app",
	data: {
		message: "Hello Vue!",
		ciclos: ["1", "2", "3"],
		selectedCiclo: url.search.split("=")[1]
			? url.search.split("=")[1]
			: "2",
		selecredSafra: "2023/2024",
		safras: ["2022/2023", "2023/2024"],
		plantio: plantio,
		colheita: colheita,
		variedades: [...new Set(filterVar)],
		variedadesDif: [...new Set(filterVarDif)],
		filteredCutulre: "Todas",
		filteredCutulreDif: "",
		selected: "",
		viewAllVareidades: true,
		style: {
			color: "whitesmoke",
			backgroundColor: "blue"
		},
		styleTitle: {
			color: "whitesmoke",
			backgroundColor: "blue"
		},
		imageField: "soy"
	},
	methods: {
		navGo() {
			console.log("gogogo");
			window.location = this.customUrl;
		},
		viewVaris() {
			console.log("Working");
			console.log(this.getFilteredChildren("Cervo"));
			this.viewAllVareidades = !this.viewAllVareidades;
		},
		greet: function (name) {
			console.log("Hello from " + name + "!");
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
		},
		getFilteredChildren(filter) {
			console.log(filter);
			console.log(this.filteredArrayByVariedade);
			return "teste 1 ";
		}
	},
	watch: {
		filteredCutulre() {
			if (this.filteredCutulre === "Todas") {
				this.style.backgroundColor = "blue";
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
			return `/admin/diamante/plantiodetailplantio/?ciclo=${this.selectedCiclo}`;
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
							areaPlantada: +curr.area_plantada,
							saldoPlantio:
								Number(curr.area_total) -
								Number(curr.area_plantada)
						};
					} else {
						acc[newObj]["areaTotal"] += Number(curr.area_total);
						acc[newObj]["areaPlantada"] += +curr.area_plantada;
						acc[newObj]["saldoPlantio"] +=
							Number(curr.area_total) -
							Number(curr.area_plantada);
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

			// for (let i = 0; i < filtColheita.length; i++) {
			// 	const nameDict =
			// 		`${filtColheita[i]["plantio__talhao__fazenda__nome"]}` +
			// 		"|" +
			// 		`${filtColheita[i]["plantio__variedade__cultura__cultura"]}`;

			// 	if (newDict[nameDict]) {
			// 		if (newDict[nameDict]["pesoColhido"] > 0) {
			// 			newDict[nameDict]["pesoColhido"] += Number(
			// 				filtColheita[i].peso_scs
			// 			);
			// 			newDict[nameDict]["produtividade"] =
			// 				newDict[nameDict]["pesoColhido"] /
			// 				Number(newDict[nameDict]["areaColheita"]);
			// 		} else {
			// 			newDict[nameDict]["pesoColhido"] = Number(
			// 				filtColheita[i].peso_scs
			// 			);
			// 			newDict[nameDict]["produtividade"] =
			// 				Number(filtColheita[i].peso_scs) /
			// 				Number(newDict[nameDict]["areaColheita"]);
			// 		}
			// 	}
			// }
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
							areaPlantada: Number(curr.area_plantada),
							saldoPlantio:
								Number(curr.area_total) -
								Number(curr.area_plantada)
						};
					} else {
						acc[newObj]["areaTotal"] += Number(curr.area_total);
						acc[newObj]["areaPlantada"] += Number(
							curr.area_plantada
						);
						acc[newObj]["saldoPlantio"] +=
							Number(curr.area_total) -
							Number(curr.area_plantada);
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

			return newDict;
		},
		newTotals() {
			let newTotals = {};
			for (const [key, value] of Object.entries(this.filteredArray)) {
				if (!newTotals["saldoPlantio"]) {
					newTotals["saldoPlantio"] = value.saldoPlantio;
				} else {
					newTotals["saldoPlantio"] += value.saldoPlantio;
				}

				if (!newTotals["areaTotal"]) {
					newTotals["areaTotal"] = value.areaTotal;
				} else {
					newTotals["areaTotal"] += value.areaTotal;
				}

				if (!newTotals["areaPlantada"]) {
					newTotals["areaPlantada"] = value.areaPlantada;
				} else {
					newTotals["areaPlantada"] += value.areaPlantada;
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
