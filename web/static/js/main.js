document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("singlePredictForm");
    var resultBox = document.getElementById("singlePredictResult");

    if (form && resultBox) {
        form.addEventListener("submit", function (e) {
            e.preventDefault();

            if (!form.reportValidity()) return;

            var submitButton = form.querySelector('button[type="submit"]');
            submitButton.disabled = true;
            submitButton.textContent = "Menghitung prediksi...";

            var formData = new FormData(form);
            var payload = {};

            formData.forEach(function (value, key) {
                payload[key] = value === "" ? null : Number(value);
            });

            resultBox.classList.remove("d-none");
            resultBox.classList.remove("alert-success", "alert-warning", "alert-danger");
            resultBox.classList.add("alert-info");
            resultBox.textContent = "Sedang menghitung prediksi...";

            fetch("/api/predict", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            })
                .then(function (res) {
                    if (!res.ok) {
                        return res.json().then(function (data) {
                            throw new Error(data.error || "Request failed");
                        });
                    }
                    return res.json();
                })
                .then(function (data) {
                    var p = data.waste_proba;
                    var level = data.risk_level;
                    var levelLabel = { High: "Tinggi", Medium: "Sedang", Low: "Rendah" }[level] || level;

                    var percent = (p * 100).toFixed(1) + "%";
                    var text =
                        "Tingkat risiko: " +
                        levelLabel +
                        " · Estimasi probabilitas food waste: " +
                        percent;

                    resultBox.classList.remove("alert-info");
                    resultBox.textContent = text;

                    if (level === "High") {
                        resultBox.classList.add("alert-danger");
                    } else if (level === "Medium") {
                        resultBox.classList.add("alert-warning");
                    } else {
                        resultBox.classList.add("alert-success");
                    }
                })
                .catch(function (err) {
                    resultBox.classList.remove("alert-info");
                    resultBox.classList.add("alert-danger");
                    resultBox.textContent = "Prediksi gagal: " + err.message;
                })
                .finally(function () {
                    submitButton.disabled = false;
                    submitButton.innerHTML = 'Prediksi risiko <span aria-hidden="true">↗</span>';
                });
        });
    }

    var uploadForm = document.getElementById("uploadForm");
    if (uploadForm) {
        var fileInput = document.getElementById("data-file");
        var selectedFile = document.getElementById("selected-file");
        var filePicker = document.getElementById("file-picker");
        fileInput.addEventListener("change", function () {
            var file = fileInput.files && fileInput.files[0];
            selectedFile.textContent = file ? "Siap diunggah: " + file.name : "Belum ada file dipilih";
            filePicker.classList.toggle("has-file", Boolean(file));
        });
        uploadForm.addEventListener("submit", function () {
            if (!uploadForm.reportValidity()) return;
            var button = uploadForm.querySelector('button[type="submit"]');
            button.disabled = true;
            button.textContent = "Mengunggah & menganalisis...";
        });
    }

    document.querySelectorAll(".review-form").forEach(function (reviewForm) {
        var statusField = reviewForm.querySelector('select[name="status"]');
        var noteField = reviewForm.querySelector('textarea[name="note"]');
        statusField.addEventListener("change", function () {
            noteField.required = statusField.value === "completed";
        });
    });

    var adminRole = document.getElementById("admin-role");
    var adminBranch = document.getElementById("admin-branch");
    if (adminRole && adminBranch) {
        function updateBranchField() {
            var isBranch = adminRole.value === "branch";
            adminBranch.required = isBranch;
            adminBranch.disabled = !isBranch;
            if (!isBranch) adminBranch.value = "";
        }
        adminRole.addEventListener("change", updateBranchField);
        updateBranchField();
    }
});
