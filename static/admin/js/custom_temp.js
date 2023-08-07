console.log("Plantio");
console.log(plantio);
console.log("Colheita");
console.log(colheita);

var app = new Vue({
	delimiters: ["[[", "]]"],
	el: "#app",
	data: {
		message: "Hello Vue!",
		plantio: plantio,
		colheita: colheita
	},
	methods: {
		greet: function (name) {
			console.log("Hello from " + name + "!");
		}
	}
});
