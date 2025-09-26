// Camera FOV Calculator JS
let jsonData = null;
const dropArea = document.getElementById('drop-area');
const inputFile = document.getElementById('inputFile');
const browseBtn = document.getElementById('browseBtn');
const resultDiv = document.getElementById('result');
const fovDiv = document.getElementById('fov');
const editArea = document.getElementById('edit-area');
const jsonEdit = document.getElementById('jsonEdit');
const updateBtn = document.getElementById('updateBtn');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

dropArea.addEventListener('dragover', () => {
    dropArea.style.background = '#e3e3e3';
});
dropArea.addEventListener('dragleave', () => {
    dropArea.style.background = '#fafafa';
});
dropArea.addEventListener('drop', handleDrop, false);

function handleDrop(e) {
    dropArea.style.background = '#fafafa';
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length) {
        inputFile.files = files;
        handleFile(files[0]);
        dropArea.querySelector('p').textContent = `Selected: ${files[0].name}`;
    }
}

browseBtn.addEventListener('click', () => {
    inputFile.click();
});
inputFile.addEventListener('change', () => {
    if (inputFile.files.length) {
        handleFile(inputFile.files[0]);
        dropArea.querySelector('p').textContent = `Selected: ${inputFile.files[0].name}`;
    }
});

function handleFile(file) {
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            jsonData = JSON.parse(e.target.result);
            showJson(jsonData);
            showEdit(jsonData);
            calculateAndDisplayFov(jsonData);
        } catch (err) {
            resultDiv.innerHTML = '<span style="color:red">Invalid JSON file.</span>';
            editArea.style.display = 'none';
            fovDiv.innerHTML = '';
        }
    };
    reader.readAsText(file);
}

function showJson(data) {
    resultDiv.innerHTML = '<h3>JSON Data</h3><pre>' + JSON.stringify(data, null, 2) + '</pre>';
}

function showEdit(data) {
    editArea.style.display = 'block';
    jsonEdit.value = JSON.stringify(data, null, 2);
}

updateBtn.onclick = function() {
    try {
        const edited = JSON.parse(jsonEdit.value);
        jsonData = edited;
        showJson(jsonData);
        calculateAndDisplayFov(jsonData);
    } catch (err) {
        alert('Invalid JSON. Please fix errors and try again.');
    }
};

function calculateAndDisplayFov(data) {
    if (!data.pinhole || !data.resolution) {
        fovDiv.innerHTML = '<span style="color:red">Missing pinhole or resolution field.</span>';
        return;
    }
    const cam = data.pinhole;
    const res = data.resolution;
    // camera_matrix: [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
    const fx = cam.camera_matrix[0][0];
    const fy = cam.camera_matrix[1][1];
    const width = res.width;
    const height = res.height;
    // FOV = 2 * arctan(size/(2*f))
    const fovX = 2 * Math.atan(width / (2 * fx)) * 180 / Math.PI;
    const fovY = 2 * Math.atan(height / (2 * fy)) * 180 / Math.PI;
    fovDiv.innerHTML = `<div class="fov">Horizontal FOV: <b>${fovX.toFixed(2)}°</b><br>Vertical FOV: <b>${fovY.toFixed(2)}°</b></div>`;
}
