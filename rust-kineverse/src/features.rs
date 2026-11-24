//! Static gesture feature extraction from 21 MediaPipe landmarks.

use crate::types::{
    FeatureInfo, GestureConfig, GestureLabel, Point3D, MCPS, NUM_LANDMARKS, TIPS,
};

#[inline(always)]
pub fn clip(v: f32, lo: f32, hi: f32) -> f32 {
    v.max(lo).min(hi)
}

/// Extract static gesture features and classify pose
///
/// Returns: (GestureLabel, confidence, FeatureInfo)
pub fn extract_features(
    landmarks: &[Point3D; NUM_LANDMARKS],
    cfg: &GestureConfig,
    aspect: f32,
    pinching: bool,
) -> (GestureLabel, f32, FeatureInfo) {
    // 1. Transform landmarks with aspect ratio for isotropic space
    let mut p = *landmarks;
    for pt in p.iter_mut() {
        pt.x *= aspect;
        pt.z *= aspect;
    }

    // 2. Hand size reference (average distance from wrist (0) to base of MCP joints 5, 9, 13)
    let d0_5 = p[0].distance_to(&p[5]);
    let d0_9 = p[0].distance_to(&p[9]);
    let d0_13 = p[0].distance_to(&p[13]);
    let hand_size = ((d0_5 + d0_9 + d0_13) / 3.0).max(1e-6);

    // 3. Extension score for each of the 4 fingers (index, middle, ring, pinky)
    let mut ext = [0.0f32; 4];
    for i in 0..4 {
        let tip = TIPS[i];
        let mcp = MCPS[i];
        let r = p[tip].distance_to(&p[0]) / p[mcp].distance_to(&p[0]).max(1e-6);
        ext[i] = clip((r - 1.25) / 0.45, 0.0, 1.0);
    }

    // 4. Pinch and Ring Shape metrics
    let pinch_ratio = p[4].distance_to(&p[8]) / hand_size;

    // Palm center (points: 0, 5, 9, 13, 17)
    let center = Point3D::new(
        (p[0].x + p[5].x + p[9].x + p[13].x + p[17].x) / 5.0,
        (p[0].y + p[5].y + p[9].y + p[13].y + p[17].y) / 5.0,
        (p[0].z + p[5].z + p[9].z + p[13].z + p[17].z) / 5.0,
    );

    let pinch_mid = Point3D::new(
        (p[4].x + p[8].x) * 0.5,
        (p[4].y + p[8].y) * 0.5,
        (p[4].z + p[8].z) * 0.5,
    );
    let reach = pinch_mid.distance_to(&center) / hand_size;
    let idx_out = p[8].distance_to(&p[5]) / hand_size;

    let shape = 0.5 * clip((idx_out - cfg.idx_out_lo) / cfg.idx_out_span, 0.0, 1.0)
        + 0.5 * clip((reach - cfg.reach_lo) / cfg.reach_span, 0.0, 1.0);

    let info = FeatureInfo {
        ext,
        pinch_ratio,
        ring_shape: shape,
    };

    // 5. Test PINCH first
    let thr = if pinching { cfg.pinch_off } else { cfg.pinch_on };
    let shape_min = if pinching {
        cfg.pinch_shape_hold
    } else {
        cfg.pinch_shape_min
    };

    if pinch_ratio < thr && shape >= shape_min {
        let conf = 0.65 + 0.2 * clip(1.0 - pinch_ratio / cfg.pinch_on, 0.0, 1.0) + 0.15 * shape;
        return (GestureLabel::Pinch, conf.min(1.0), info);
    }

    // 6. Test finger extension patterns
    let up = [
        ext[0] > 0.5,
        ext[1] > 0.5,
        ext[2] > 0.5,
        ext[3] > 0.5,
    ];

    let margin = |want: [bool; 4]| -> f32 {
        let mut m = 1.0f32;
        for i in 0..4 {
            let score = if want[i] { ext[i] } else { 1.0 - ext[i] };
            if score < m {
                m = score;
            }
        }
        m
    };

    if up == [true, true, true, true] {
        return (GestureLabel::OpenPalm, margin([true, true, true, true]), info);
    }
    if up == [false, false, false, false] {
        return (GestureLabel::Fist, margin([false, false, false, false]), info);
    }
    if up == [true, false, false, false] {
        return (GestureLabel::Pointing, margin([true, false, false, false]), info);
    }
    if up == [true, true, false, false] {
        return (GestureLabel::TwoFingers, margin([true, true, false, false]), info);
    }

    (GestureLabel::Unknown, 0.0, info)
}
