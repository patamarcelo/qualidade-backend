const filterVariedades = plantio.map((data, i) => {
	return data.variedade__cultura__cultura;
});

const filterVariedadesDif = plantio.map((data, i) => {
	return `${data.variedade__cultura__cultura} - ${data.variedade__variedade}`;
});

const filterVar = ["Todas", ...filterVariedades];
const filterVarDif = ["Todas", ...filterVariedadesDif];

console.log(colheita)
var app = new Vue({
	delimiters: ["[[", "]]"],
	el: "#app",
	data: {
		message: "Hello Vue!",
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
		imageField: "soy"
	},
	methods: {
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
