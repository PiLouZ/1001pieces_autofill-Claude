/**
 * Title : Générateur de fiche produit
 * Auteur : PL SILLIERE / ChatGPT
 * V2.1.2
 */


const form = document.getElementById('form-generator');
const titreElement = document.getElementById('titre');
const textareaTitreElement = document.getElementById('textarea-titre');
const descriptionElement = document.getElementById('description');
const textareaTitre = document.getElementById('textarea-titre');
const textareaDesc = document.getElementById('textarea-desc');
const titreCounter = document.getElementById('titre-counter');
const descCounter = document.getElementById('desc-counter');
const marquesMajuscules = ['AEG', 'LG', 'CDA', 'SKG', 'XD'];
// Regroupements des catégories
const categoryMapping = {
	"Four vapeur": "Four",
	"Four à chaleur tournante": "Four",
	"Four micro-ondes": "Micro-ondes",
	"Table": "Plaque",
	"LV": "Lave-vaisselle",
	"LL": "Lave-linge",
	"SL": "Sèche-linge",
	"Frigo": "Réfrigérateur",
	"Congèlo": "Congélateur",
	"LS": "Lavante-séchante"
	// Complétez la liste ici
};

form.addEventListener('submit', function (event) {
	event.preventDefault();
	generateMeta();
	afficherListe();
});

function generateMeta() {
	const texte = document.getElementById('text').value;
	var titleErrorElement = document.getElementById("titleError");

	const exp_titre = /(.*) - (.*)/i;
	const exp_desc = /(.*) pour (.*) - (.*)/i;

	if (texte.trim() === "") {
		return;
	} else if (!exp_desc.test(texte)) {
		titleErrorElement.style.display = "block";
		return; // Arrêter l'exécution de la fonction si le format n'est pas valide
	} else {
		titleErrorElement.style.display = "none";
	}

	const balise_titre = texte.replace(exp_desc, function (match, p1, p2, p3) {
		const wordsP2 = p2.split(' ');
		const modifiedP2 = wordsP2.map(word => wordsToLowercase.includes(word) ? word.toLowerCase() : word).join(' ');
		return `${p3} - ${p1} pour ${modifiedP2}`;
	});
	const adjustedTitle = adjustTitleLength(balise_titre); // Appel de la fonction adjustTitleLength

	const balise_desc = texte.replace(exp_desc, function (match, p1, p2, p3) {
		const wordsP2 = p2.split(' ');
		const modifiedP2 = wordsP2.map(word => wordsToLowercase.includes(word) ? word.toLowerCase() : word).join(' ');
		const variantes = [
      `Commandez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} chez un expert des pièces détachées pour appareil électroménager`,
      `Obtenez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} auprès d'un spécialiste des pièces détachées pour appareils électroménagers`,
      `Achetez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} chez un fournisseur fiable de pièces détachées pour appareils électroménagers`,
      `Découvrez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} et réparez vos appareils électroménagers en toute simplicité`,
      `Trouvez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} chez le spécialiste des pièces détachées`,
      `Commandez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} chez un expert de la réparation d'appareils électroménagers`,
      `Obtenez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} et réparez facilement vos appareils électroménagers`,
      `Achetez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} et redonnez vie à vos appareils électroménagers`,
      `Découvrez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} et réparez vos appareils électroménagers en toute simplicité`,
      `Trouvez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} chez le spécialiste des pièces détachées pour la réparation d'appareils électroménagers`,
      `Retrouvez ${getArticle(p1, p3)} ${uncapitalizeFirstLetter(p1)} ${p3} pour ${modifiedP2} pour répararer vos appareils électroménagers`,
      // Ajoutez autant de variantes que vous le souhaitez
    ];

		let validVariants = variantes.filter(description => description.length <= 150);

		let description = '';
		if (validVariants.length > 0) {
			description = validVariants[Math.floor(Math.random() * validVariants.length)];
		} else {
			description = variantes[Math.floor(Math.random() * variantes.length)];
		}

		if (description.length > 150) {
			description = description.slice(0, 147) + '...';
			descriptionElement.style.color = 'red';
		} else {
			descriptionElement.style.color = '';
		}

		return description;
	});

	const balise_titre_length = adjustedTitle.length;
	const balise_desc_length = balise_desc.length;

	titreElement.innerHTML = `Titre <span id="titre-counter" class="counter text-muted">${balise_titre_length}/60 caractères</span>`;
	descriptionElement.innerHTML = `Description <span id="desc-counter" class="counter text-muted">${balise_desc_length}/150 caractères</span>`;
	textareaTitre.value = adjustedTitle;
	textareaDesc.value = balise_desc;

	if (balise_titre_length > 60) {
		titreElement.style.color = '#dc3545';
		textareaTitreElement.style.color = '#dc3545';
	} else {
		titreElement.style.color = '';
		textareaTitreElement.style.color = '#212529';
	}
}

function getArticle(p1, p3) {
	const firstWord = p1.split(' ')[0];
	const isPlural = firstWord.endsWith('s') || firstWord.endsWith('x');

	return isPlural ? 'vos' : 'votre';
}

function uncapitalizeFirstLetter(string) {
	return string.charAt(0).toLowerCase() + string.slice(1);
}

function adjustTitleLength(title) {
	const maxTitleLength = 60;

	let adjustedTitle = title.trim();
	let words = adjustedTitle.split(" ");

	for (let i = 0; i < excludedWords.length; i++) {
		const excludedWord = excludedWords[i];
		while (adjustedTitle.length > maxTitleLength) {
			let wordRemoved = false;
			for (let j = 0; j < words.length; j++) {
				const word = words[j];
				if (word.toLowerCase() === excludedWord.toLowerCase()) {
					words.splice(j, 1);
					adjustedTitle = words.join(" ");
					wordRemoved = true;
					break;
				}
			}
			if (!wordRemoved) {
				break;
			}
		}
	}

	if (adjustedTitle.length > maxTitleLength) {
		for (const word in wordReplacements) {
			if (adjustedTitle.includes(word)) {
				adjustedTitle = adjustedTitle.replace(new RegExp(`\\b${word}\\b`, "gi"), wordReplacements[word]);
			}
			if (adjustedTitle.length <= maxTitleLength) {
				break;
			}
		}
	}

	return adjustedTitle;
}


function inverserTableau(tableau) {
    tableau.sort((a, b) => a[0].localeCompare(b[0]));
    let listeOrdonnee = [];
    let categorie = "";

    for (let i = 0; i < tableau.length; i++) {
        let [marque, modele] = tableau[i];
        if (marque !== categorie) {
            if (listeOrdonnee.length > 0) {
                listeOrdonnee.push("<div>&nbsp;</div>");
            }
            categorie = marque;
            listeOrdonnee.push(`<div id='${marque}'><b><u>${marque}</u></b></div>`);
        }
        listeOrdonnee.push(`<div>${modele}</div>`);
    }

    return listeOrdonnee;
}

function afficherListe() {
	let data = document.getElementById('tableau').value.trim();
	let lines = data.split('\n');
	let lignesSupprimees = 0;

	let marques = new Set();
	let appareils = new Set();
	let tableau = [];

	lines = lines
		.map(line => line.trim())
		.filter((line, index, self) => {
			if (self.indexOf(line) !== index) {
				lignesSupprimees++;
				return false;
			}
			return true;
		})
		.sort((a, b) => a.localeCompare(b));

	for (let i = 0; i < lines.length; i++) {
		let cols = lines[i].split('\t');
		if (cols.length >= 3) {
			let marque = cols[1].trim();

			// ✅ Si la marque correspond à l'une des entrées (sans tenir compte de la casse), on la remplace en majuscules
			marque = marque
			.toLowerCase()
			.split(/(\s+|-)/) // Garde les espaces et tirets comme séparateurs
			.map(part => marquesMajuscules.includes(part.toUpperCase()) ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1))
			.join("");

			let fusionColonnes = cols.slice(2).join(' - ').trim();
			tableau.push([marque, fusionColonnes]);
			marques.add(marque);
			appareils.add(fusionColonnes);
		}
	}

	let listeOrdonneeInversee = inverserTableau(tableau);
	document.getElementById('listeInversee').innerHTML = listeOrdonneeInversee.join('\n');

	let marquesHTML = Array.from(marques).sort().map(marque => `<a href="#${marque}">${marque}</a>`).join(' ');
	document.getElementById('listeMarque').innerHTML = marquesHTML;

	let titleErrorElement = document.getElementById("nbSuppression");
	titleErrorElement.style.display = lignesSupprimees > 0 ? "block" : "none";
	if (lignesSupprimees > 0) {
		titleErrorElement.innerHTML = `Nombre de lignes supprimées : ${lignesSupprimees}`;
	}
}


function copierCode(elementId) {
	var listeInversee = document.getElementById(elementId);
	var listeInverseeHtml = listeInversee.innerHTML;

	var tempTextArea = document.createElement("textarea");
	tempTextArea.value = listeInverseeHtml;
	document.body.appendChild(tempTextArea);

	tempTextArea.select();
	document.execCommand("copy");
	document.body.removeChild(tempTextArea);

	//alert("Liste copiée !");
}

function copyText(elementId) {
	const textarea = document.getElementById(elementId);
	textarea.select();
	document.execCommand('copy');
}

function selectContent(inputField) {
	inputField.select();
}

function clearTableau() {
	document.getElementById("tableau").value = ""; // Efface le contenu de la zone de texte
	afficherListe(); // Met à jour la liste inversée
}

function enregistrerCSV() {
	let refProduct = document.getElementById("refProduct").value.trim() || "export";
	let data = document.getElementById("tableau").value.trim();
	let lines = data.split("\n");
	let csvContent = "product;type;manufacturer;modele_name;reference_modele;commercial_reference\n";

	for (let line of lines) {
		let cols = line.split("\t");
		if (cols.length >= 4) {
			let reference = refProduct;
			let rawCategorie = cols[0].trim();
            let categorie = categoryMapping[rawCategorie] || rawCategorie;
			let marque = cols[1].trim();

			// ✅ Si la marque correspond à l'une des entrées (sans tenir compte de la casse), on la remplace en majuscules
			marque = marque
			.toLowerCase()
			.split(/(\s+|-)/) // Garde les espaces et tirets comme séparateurs
			.map(part => marquesMajuscules.includes(part.toUpperCase()) ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1))
			.join("");

			let modele = cols.slice(2).join(" - ").trim();
			let refTechnique = cols[2].trim();
			let refCommerciale = cols[3].trim();
			csvContent += `${reference};${categorie};${marque};${modele};${refTechnique};${refCommerciale}\n`;
		}
	}

	let blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
	let link = document.createElement("a");
	link.href = URL.createObjectURL(blob);
	link.download = `${refProduct}.csv`;
	link.click();
}



// Initialiser manuellement les infobulles
var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
	return new bootstrap.Tooltip(tooltipTriggerEl);
});
