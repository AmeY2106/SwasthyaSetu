// Leaflet.js ambulance tracking with AJAX polling
function initAmbulanceTracker(opts) {
  const {
    mapId, ambulanceId, hospitalLat, hospitalLng, hospitalName,
    patientLat, patientLng, initialAmbLat, initialAmbLng, pollInterval = 10000,
  } = opts;

  const map = L.map(mapId).setView([initialAmbLat, initialAmbLng], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map);

  // Custom icons
  const ambIcon = L.divIcon({
    html: '<div style="background:#dc3545;color:#fff;width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(220,53,69,0.5);font-size:1.2rem;border:3px solid #fff;"><i class="bi bi-truck"></i></div>',
    className: 'amb-marker', iconSize: [42, 42], iconAnchor: [21, 21],
  });
  const hospitalIcon = L.divIcon({
    html: '<div style="background:#0a7c6b;color:#fff;width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(10,124,107,0.5);border:3px solid #fff;"><i class="bi bi-hospital"></i></div>',
    className: 'hosp-marker', iconSize: [38, 38], iconAnchor: [19, 19],
  });
  const patientIcon = L.divIcon({
    html: '<div style="background:#0d6efd;color:#fff;width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(13,110,253,0.5);border:3px solid #fff;"><i class="bi bi-person-fill"></i></div>',
    className: 'patient-marker', iconSize: [38, 38], iconAnchor: [19, 19],
  });

  const ambMarker = L.marker([initialAmbLat, initialAmbLng], { icon: ambIcon })
    .addTo(map).bindPopup('<b>Ambulance</b>');
  const hospitalMarker = L.marker([hospitalLat, hospitalLng], { icon: hospitalIcon })
    .addTo(map).bindPopup('<b>' + hospitalName + '</b>');
  const patientMarker = (patientLat && patientLng)
    ? L.marker([patientLat, patientLng], { icon: patientIcon }).addTo(map).bindPopup('<b>Patient pickup</b>')
    : null;

  let route = L.polyline([
    [hospitalLat, hospitalLng],
    [initialAmbLat, initialAmbLng],
    ...(patientLat && patientLng ? [[patientLat, patientLng]] : []),
  ], { color: '#dc3545', weight: 4, opacity: 0.8, dashArray: '8 6' }).addTo(map);

  // Fit bounds
  const bounds = L.latLngBounds([[hospitalLat, hospitalLng], [initialAmbLat, initialAmbLng]]);
  if (patientLat && patientLng) bounds.extend([patientLat, patientLng]);
  map.fitBounds(bounds, { padding: [40, 40] });

  const refresh = async () => {
    try {
      const res = await fetch(`/api/ambulance/${ambulanceId}/status`);
      if (!res.ok) return;
      const data = await res.json();

      // Move ambulance
      ambMarker.setLatLng([data.latitude, data.longitude]);
      ambMarker.setPopupContent(`<b>${data.ambulance_number}</b><br>Status: ${data.status}<br>Driver: ${data.driver_name}`);

      // Update route
      const points = [[data.hospital_lat, data.hospital_lng], [data.latitude, data.longitude]];
      if (data.patient_lat && data.patient_lng) points.push([data.patient_lat, data.patient_lng]);
      route.setLatLngs(points);

      // Update UI panel
      const statusEl = document.getElementById('amb-status');
      const etaEl = document.getElementById('amb-eta');
      const latEl = document.getElementById('amb-lat');
      const lngEl = document.getElementById('amb-lng');
      const updEl = document.getElementById('amb-updated');
      if (statusEl) {
        statusEl.textContent = data.status.replace('_', ' ').toUpperCase();
        statusEl.className = 'status-badge status-' + data.status;
      }
      if (etaEl && data.eta_minutes != null) etaEl.textContent = data.eta_minutes;
      if (latEl) latEl.textContent = data.latitude.toFixed(5);
      if (lngEl) lngEl.textContent = data.longitude.toFixed(5);
      if (updEl) updEl.textContent = new Date(data.updated_at).toLocaleTimeString();
    } catch (e) { console.warn('Tracking refresh failed:', e); }
  };

  setInterval(refresh, pollInterval);
  refresh();
  return map;
}
