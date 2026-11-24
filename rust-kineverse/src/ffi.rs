//! C-ABI Foreign Function Interface (FFI) for Python ctypes and C/C++ embedding.

use crate::engine::GestureEngine;
use crate::features::extract_features;
use crate::one_euro::OneEuro3D;
use crate::types::{
    FeatureInfo, GestureAction, GestureConfig, GestureLabel, Point3D, RawGestureEvent,
    NUM_LANDMARKS,
};

#[no_mangle]
pub extern "C" fn kineverse_create_engine() -> *mut GestureEngine {
    let engine = Box::new(GestureEngine::new(GestureConfig::default()));
    Box::into_raw(engine)
}

#[no_mangle]
pub extern "C" fn kineverse_destroy_engine(engine: *mut GestureEngine) {
    if !engine.is_null() {
        unsafe {
            drop(Box::from_raw(engine));
        }
    }
}

#[no_mangle]
pub extern "C" fn kineverse_extract_features(
    landmarks_ptr: *const f32, // Array of 21 * 3 = 63 floats [x0, y0, z0, x1, y1, z1, ...]
    aspect: f32,
    pinching: bool,
    out_label: *mut u8,
    out_confidence: *mut f32,
    out_info: *mut FeatureInfo,
) -> bool {
    if landmarks_ptr.is_null() {
        return false;
    }

    let mut lms = [Point3D::default(); NUM_LANDMARKS];
    unsafe {
        for i in 0..NUM_LANDMARKS {
            lms[i] = Point3D::new(
                *landmarks_ptr.add(i * 3),
                *landmarks_ptr.add(i * 3 + 1),
                *landmarks_ptr.add(i * 3 + 2),
            );
        }
    }

    let cfg = GestureConfig::default();
    let (label, conf, info) = extract_features(&lms, &cfg, aspect, pinching);

    unsafe {
        if !out_label.is_null() {
            *out_label = label as u8;
        }
        if !out_confidence.is_null() {
            *out_confidence = conf;
        }
        if !out_info.is_null() {
            *out_info = info;
        }
    }

    true
}

#[no_mangle]
pub extern "C" fn kineverse_process_frame(
    engine: *mut GestureEngine,
    landmarks_ptr: *const f32, // Null if hand is lost
    aspect: f32,
    timestamp: f64,
    out_events_buffer: *mut RawGestureEvent,
    buffer_capacity: usize,
    out_event_count: *mut usize,
) -> bool {
    if engine.is_null() || out_event_count.is_null() {
        return false;
    }

    let engine_ref = unsafe { &mut *engine };
    let mut events = Vec::with_capacity(8);

    if landmarks_ptr.is_null() {
        engine_ref.on_hand_lost(timestamp, &mut events);
    } else {
        let mut lms = [Point3D::default(); NUM_LANDMARKS];
        unsafe {
            for i in 0..NUM_LANDMARKS {
                lms[i] = Point3D::new(
                    *landmarks_ptr.add(i * 3),
                    *landmarks_ptr.add(i * 3 + 1),
                    *landmarks_ptr.add(i * 3 + 2),
                );
            }
        }

        let pinching = engine_ref.is_pinching();
        let (label, conf, _) = extract_features(&lms, &engine_ref.cfg, aspect, pinching);
        engine_ref.process_static(label, conf, timestamp, &mut events);

        // Track palm center (joint 9: MCP of middle finger)
        let palm_x = lms[9].x;
        let palm_y = lms[9].y;
        engine_ref.process_motion(palm_x, palm_y, timestamp, &mut events);
    }

    let copy_count = events.len().min(buffer_capacity);
    unsafe {
        if !out_events_buffer.is_null() && copy_count > 0 {
            std::ptr::copy_nonoverlapping(events.as_ptr(), out_events_buffer, copy_count);
        }
        *out_event_count = copy_count;
    }

    true
}

#[no_mangle]
pub extern "C" fn kineverse_create_one_euro(
    min_cutoff: f32,
    beta: f32,
    d_cutoff: f32,
) -> *mut OneEuro3D {
    let filter = Box::new(OneEuro3D::new(min_cutoff, beta, d_cutoff));
    Box::into_raw(filter)
}

#[no_mangle]
pub extern "C" fn kineverse_destroy_one_euro(filter: *mut OneEuro3D) {
    if !filter.is_null() {
        unsafe {
            drop(Box::from_raw(filter));
        }
    }
}

#[no_mangle]
pub extern "C" fn kineverse_filter_point(
    filter: *mut OneEuro3D,
    x: f32,
    y: f32,
    z: f32,
    t: f64,
    out_x: *mut f32,
    out_y: *mut f32,
    out_z: *mut f32,
) -> bool {
    if filter.is_null() {
        return false;
    }
    let filter_ref = unsafe { &mut *filter };
    let filtered = filter_ref.filter(Point3D::new(x, y, z), t);
    unsafe {
        if !out_x.is_null() {
            *out_x = filtered.x;
        }
        if !out_y.is_null() {
            *out_y = filtered.y;
        }
        if !out_z.is_null() {
            *out_z = filtered.z;
        }
    }
    true
}
