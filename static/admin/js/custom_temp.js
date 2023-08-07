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
		selected: "",
		options: [
			{ id: 0, labels: "Vegetables" },
			{ id: 1, labels: "Cheese" },
			{ id: 2, labels: "Fruits" }
		]
	},
	methods: {
		greet: function (name) {
			console.log("Hello from " + name + "!");
		}
	},
	computed: {
		filteredArray() {
			console.log(this.plantio);
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
			this.colheita
				.filter((data) =>
					this.filteredCutulre == "Todas"
						? data.variedade__cultura__cultura !== "nenhuma"
						: data.variedade__cultura__cultura ===
						  this.filteredCutulre
				)
				.map((data, i) => {
					const area =
						newDict[
							data.plantio__talhao__fazenda__nome +
								"|" +
								data.plantio__variedade__cultura__cultura
						].areaColheita;

					newDict[
						data.plantio__talhao__fazenda__nome +
							"|" +
							data.plantio__variedade__cultura__cultura
					].pesoColhido = Number(data.peso_scs);

					newDict[
						data.plantio__talhao__fazenda__nome +
							"|" +
							data.plantio__variedade__cultura__cultura
					].produtividade = Number(
						Number(data.peso_scs) / Number(area)
					);
				});
			console.log(newDict);
			return newDict;
		}
	}
});
