import { Router } from 'express';
import librosRouter from './libros.routes.js';

const router = Router();

router.get('/health', (req, res) => res.json({ ok: true, servicio: 'biblioteca-virtual' }));
router.use('/libros', librosRouter);

export default router;
