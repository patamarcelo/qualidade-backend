console.log("Plantio");
console.log(plantio);
console.log("Colheita");
console.log(colheita);

const filterVariedades = plantio.map((data, i) => {
	return data.variedade__cultura__cultura;
});

const filterVar = ["Todas", ...filterVariedades];

var app = new Vue({
	delimiters: ["[[", "]]"],
	el: "#app",
	data: {
		message: "Hello Vue!",
		plantio: plantio,
		colheita: colheita,
		variedades: [...new Set(filterVar)],
		filteredCutulre: "Todas",
		selected: ""
	},
	methods: {
		greet: function (name) {
			console.log("Hello from " + name + "!");
		}
	},
	computed: {
		filteredArray() {
			const newDict = this.plantio
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
							areaColheita:
								Number(curr.area_parcial) +
								Number(curr.area_finalizada),
							saldoColheita:
								Number(curr.area_total) -
								Number(curr.area_parcial) -
								Number(curr.area_finalizada),
							pesoColhido: 0,
							produtividade: 0
						};
					} else {
						acc[newObj]["areaTotal"] += Number(curr.area_total);
						acc[newObj]["areaColheita"] +=
							Number(curr.area_parcial) +
							Number(curr.area_finalizada);
					}
					return acc;
				}, {});
			for (let i = 0; i < this.colheita.length; i++) {
				const nameDict =
					`${this.colheita[i]["plantio__talhao__fazenda__nome"]}` +
					"|" +
					`${this.colheita[i]["plantio__variedade__cultura__cultura"]}`;

				if (newDict[nameDict]) {
					newDict[nameDict]["pesoColhido"] = Number(
						this.colheita[i].peso_scs
					);
					newDict[nameDict]["produtividade"] =
						Number(this.colheita[i].peso_scs) /
						Number(newDict[nameDict]["areaColheita"]);
				}
			}
			console.log(newDict);
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
		}
	}
});
