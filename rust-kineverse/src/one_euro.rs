//! OneEuro filter for high precision, low-latency coordinate smoothing.

use crate::types::Point3D;
use std::f32::consts::PI;

/// OneEuro filter implementation in 3D
#[derive(Debug, Clone, Copy)]
pub struct OneEuro3D {
    pub min_cutoff: f32,
    pub beta: f32,
    pub d_cutoff: f32,
    x_prev: Option<Point3D>,
    dx_prev: Point3D,
    t_prev: f64,
}

impl OneEuro3D {
    pub fn new(min_cutoff: f32, beta: f32, d_cutoff: f32) -> Self {
        Self {
            min_cutoff,
            beta,
            d_cutoff,
            x_prev: None,
            dx_prev: Point3D::default(),
            t_prev: 0.0,
        }
    }

    #[inline(always)]
    pub fn reset(&mut self) {
        self.x_prev = None;
        self.dx_prev = Point3D::default();
        self.t_prev = 0.0;
    }

    #[inline(always)]
    fn alpha(cutoff: f32, dt: f32) -> f32 {
        let dt = dt.max(1e-4);
        let tau = 1.0 / (2.0 * PI * cutoff);
        1.0 / (1.0 + tau / dt)
    }

    /// Filter a 3D point given the current timestamp in seconds
    pub fn filter(&mut self, val: Point3D, t: f64) -> Point3D {
        let x_prev = match self.x_prev {
            Some(prev) => prev,
            None => {
                self.x_prev = Some(val);
                self.dx_prev = Point3D::default();
                self.t_prev = t;
                return val;
            }
        };

        let dt = (t - self.t_prev).max(1e-4) as f32;

        // Derivative filtering
        let a_d = Self::alpha(self.d_cutoff, dt);
        let dx_raw = Point3D::new(
            (val.x - x_prev.x) / dt,
            (val.y - x_prev.y) / dt,
            (val.z - x_prev.z) / dt,
        );

        let dx_filtered = Point3D::new(
            a_d * dx_raw.x + (1.0 - a_d) * self.dx_prev.x,
            a_d * dx_raw.y + (1.0 - a_d) * self.dx_prev.y,
            a_d * dx_raw.z + (1.0 - a_d) * self.dx_prev.z,
        );
        self.dx_prev = dx_filtered;

        // Signal filtering
        let speed = dx_filtered.norm();
        let cutoff = self.min_cutoff + self.beta * speed;
        let a = Self::alpha(cutoff, dt);

        let x_filtered = Point3D::new(
            a * val.x + (1.0 - a) * x_prev.x,
            a * val.y + (1.0 - a) * x_prev.y,
            a * val.z + (1.0 - a) * x_prev.z,
        );

        self.x_prev = Some(x_filtered);
        self.t_prev = t;
        x_filtered
    }
}
