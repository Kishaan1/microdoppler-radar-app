# Theoretical & Technical Reference — SIGMA-9 Micro-Doppler Radar System

A comprehensive theoretical and mathematical guide for the **SIGMA-9 Micro-Doppler Radar Target Classification & Perimeter Defense System**, covering radar electromagnetics, micro-motion signal processing, STFT spectrogram physics, military threat evaluation, and rendering mechanics.

---

## 1. Fundamental Radar Physics & The Doppler Effect

When a Continuous Wave (CW) or Frequency-Modulated Continuous Wave (FMCW) radar transmits an electromagnetic signal at carrier frequency $f_c$ toward a moving target, the target's radial motion causes a frequency shift in the reflected echo:

$$f_d = \frac{2 \cdot v \cdot f_c}{c}$$

Where:
- $f_d$ = Doppler frequency shift (Hz)
- $v$ = Target radial velocity relative to the radar antenna (m/s)
- $f_c$ = Carrier frequency ($24.125 \text{ GHz}$ ISM radar band)
- $c$ = Speed of light ($3.0 \times 10^8 \text{ m/s}$)

---

## 2. Micro-Doppler Effect & Physical Target Signatures

While the **bulk Doppler shift** measures the overall translation speed of the main body (e.g., a drone flying at $10\text{ m/s}$), targets possess internal moving components (rotors, wings, limbs, engines). These secondary micro-motions induce periodic frequency sidebands known as **Micro-Doppler Signatures**.

```
                           MICRO-DOPPLER FREQUENCY SIGNATURES
  
    [ 🛸 DRONE ]           [ 🦅 BIRD ]           [ 🚶 HUMAN ]          [ 🚗 VEHICLE ]
  High-freq rotor       Sinusoidal wingbeat     Biomechanical gait     Engine vibration
  flutter (80-240Hz)     modulation (3-7Hz)     limb swing (2-6Hz)    steady return (-2dB)
     ||||||||                /\/\/\/\               /\  /\  /\               ======
```

| Target Class | Velocity Envelope ($v$) | Micro-Motion Source | Micro-Doppler Spectral Signature |
| :--- | :--- | :--- | :--- |
| 🛸 **Drone / UAV** | $0.0\text{--}20.0 \text{ m/s}$ | Spinning rotor blades | High-frequency periodic flutter & wide micro-Doppler bandwidth |
| 🦅 **Bird / Avian** | $2.0\text{--}15.0 \text{ m/s}$ | Flapping wings | Low-frequency sinusoidal wingbeat modulation |
| 🚶 **Human / Foot Patrol** | $0.5\text{--}3.5 \text{ m/s}$ | Swinging arms & legs (gait) | Complex non-stationary gait cycle harmonics |
| 🚗 **Vehicle / Armor** | $5.0\text{--}35.0 \text{ m/s}$ | Engine & wheel vibration | Low spectral spread, large Radar Cross Section (RCS) |

Because micro-motion signatures depend on target geometry and mechanical dynamics, they act as an **electromagnetic fingerprint** capable of target identification regardless of weather or darkness.

---

## 3. Short-Time Fourier Transform (STFT) Spectrograms

Because radar echoes are non-stationary time series, frequency content is computed using a sliding **Short-Time Fourier Transform (STFT)** window:

$$S(t, f) = \left| \int_{-\infty}^{\infty} x(\tau) w(\tau - t) e^{-j 2 \pi f \tau} d\tau \right|^2$$

Where $x(\tau)$ is the received radar I/Q signal and $w(\tau - t)$ is a Gaussian window function.
- In **SIGMA-9**, the spectrum is discretized into **64 frequency channels** updated at **10 Hz**.
- The spectral texture variance $\sigma^2$ evaluates signature cleanliness:

$$\sigma^2 = \frac{1}{N} \sum_{i=1}^{N} (b_i - \bar{b})^2$$

---

## 4. Military Threat Priority & AI Classification Matrix (`mil-cnn-v2`)

The classification engine maps extracted feature tuples $(f_d, v, \sigma^2, \text{bins})$ into target classes and military defense priority ratings:

$$\text{Threat Priority } \mathcal{T} \in \{\text{CRITICAL}, \text{HIGH}, \text{MEDIUM}, \text{LOW}, \text{WARNING}\}$$

```
                          MILITARY DEFENSE PRIORITY MATRIX

  +-----------------------+------------------------+-------------------------------+
  | Target Class          | Defense Threat Rating  | Tactical Callsign Code        |
  +-----------------------+------------------------+-------------------------------+
  | Drone / Quadcopter    | CRITICAL 🔴           | ALPHA-DRONE-HOSTILE           |
  | Infiltrating Personnel| HIGH 🟠               | BRAVO-FOOT-INFILTRATOR        |
  | Armored Vehicle       | MEDIUM 🟣              | CHARLIE-ARMORED-VEHICLE       |
  | Avian Flight          | LOW / NEUTRAL 🟢       | AVIAN-NEUTRAL-FILTERED        |
  | Unclassified Echo     | WARNING ⚪             | DELTA-UNIDENTIFIED-ECHO       |
  +-----------------------+------------------------+-------------------------------+
```

Prediction confidence $C$ is computed with texture variance weighting:

$$C = \text{Clamp}\Big(C_{\text{base}} + \Delta_{\text{texture}}, \, 0.10, \, 0.99\Big)$$

---

## 5. Live Target PPI Scope Polar Coordinates

The **Plan Position Indicator (PPI) Scope** maps target coordinates $(\theta, r)$ onto 2D polar canvas space:

$$x = x_0 + r \cdot \cos(\theta), \quad y = y_0 + r \cdot \sin(\theta)$$

Where:
- $(x_0, y_0)$ = Radar antenna center point
- $\theta(t)$ = 360° rotating radar sweep angle ($\omega = 60^\circ/\text{sec}$)
- $r$ = Target distance estimate derived from return power $P_{\text{dB}}$ and velocity $v$

---

## 6. Single-Page Application (SPA) & Multi-Device Mechanics

1. **Unbroken Animation Loop Safety**:
   - Canvas animation functions schedule `requestAnimationFrame(renderPPIScope)` continuously, preventing loop termination when tabs switch or when parent containers are hidden.
2. **Device Viewport Switcher (`💻 Lap`, `📟 Tab`, `📱 Mobile`)**:
   - Modifies DOM body state (`body.mode-lap`, `body.mode-tab`, `body.mode-mobile`), triggering CSS viewport transitions and re-scaling canvas buffers on demand.
