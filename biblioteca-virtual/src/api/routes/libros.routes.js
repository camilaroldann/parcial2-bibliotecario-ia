import { Router } from 'express';
import * as controller from '../controllers/libros.controller.js';

/** CAPA API - Definición de rutas del recurso "libros". */
const router = Router();

router.get('/', controller.listar);
router.post('/', controller.crear);
router.get('/:id', controller.obtener);
router.patch('/:id/estado', controller.cambiarEstado);

export default router;
